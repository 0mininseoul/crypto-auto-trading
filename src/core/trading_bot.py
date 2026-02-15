"""
메인 트레이딩 봇 (Trading Bot)
전체 거래 플로우 오케스트레이션 + Discord 알림 연동
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional

from src.exchange.bitget_client import BitgetClient
from src.exchange.data_fetcher import DataFetcher
from src.exchange.websocket_client import BitgetWebSocket
from src.core.market_analyzer import MarketAnalyzer
from src.core.risk_manager import RiskManager
from src.core.order_executor import OrderExecutor
from src.core.position_manager import PositionManager
from src.indicators.signals import SignalType
from src.database.repository import BotStatusRepository, TradeRepository
from src.database.models import BotState, Trade
from src.config.constants import TIMEFRAMES
from src.config.settings import get_settings
from src.discord_bot.notifier import get_notifier
from src.utils.logger import setup_logger

logger = setup_logger("trading_bot")

# 분석 주기 (초)
ANALYSIS_INTERVAL = 60 * 15      # 15분마다 신호 분석
POSITION_CHECK_INTERVAL = 60     # 1분마다 포지션 모니터링
HEARTBEAT_INTERVAL = 60 * 5      # 5분마다 하트비트


class TradingBot:
    """메인 트레이딩 봇"""

    def __init__(self):
        self._exchange = BitgetClient()
        self._ws_client: Optional[BitgetWebSocket] = None
        self._data_fetcher: Optional[DataFetcher] = None
        self._analyzer: Optional[MarketAnalyzer] = None
        self._risk: Optional[RiskManager] = None
        self._executor: Optional[OrderExecutor] = None
        self._position_mgr: Optional[PositionManager] = None
        self._notifier = get_notifier()
        self._running = False
        self._settings = get_settings()

    def _is_paused(self) -> bool:
        """봇이 PAUSED 상태인지 DB에서 확인"""
        status = BotStatusRepository.get_status()
        if status and status.get("status") == BotState.PAUSED.value:
            return True
        return False

    async def initialize(self):
        """봇 초기화"""
        logger.info("=" * 50)
        logger.info("🤖 Bitcoin Autotrading Bot 시작")
        logger.info(f"   모드: {'🔧 데모' if self._settings.is_demo else '⚠️ 라이브'}")
        logger.info("=" * 50)

        # WebSocket 클라이언트 생성
        self._ws_client = BitgetWebSocket()

        # DataFetcher 초기화 (REST + WebSocket)
        self._data_fetcher = DataFetcher(self._exchange, self._ws_client)
        await self._data_fetcher.initialize()

        # WebSocket 실시간 데이터 시작
        try:
            await self._data_fetcher.start_realtime()
            logger.info("🔴 WebSocket 실시간 데이터 활성화")
        except Exception as e:
            logger.warning(f"WebSocket 활성화 실패, REST 전용 모드: {e}")

        # 핵심 엔진 초기화
        self._analyzer = MarketAnalyzer(self._data_fetcher)
        self._risk = RiskManager(self._exchange)
        self._executor = OrderExecutor(self._exchange, self._risk)
        self._position_mgr = PositionManager(
            self._exchange, self._executor, self._risk
        )

        # 봇 상태 업데이트
        BotStatusRepository.update_status(
            status=BotState.RUNNING,
            trading_mode=self._settings.trading_mode,
        )

        self._running = True
        logger.info("✅ 봇 초기화 완료")

    async def run(self):
        """메인 실행 루프"""
        await self.initialize()

        try:
            tasks = [
                self._analysis_loop(),
                self._position_monitor_loop(),
                self._heartbeat_loop(),
            ]
            # WebSocket 리스닝 태스크 추가
            if self._ws_client and self._ws_client.is_connected:
                tasks.append(self._ws_client.listen())

            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("봇 종료 요청")
        except Exception as e:
            logger.critical(f"🚨 봇 치명적 오류: {e}")
            await self._notifier.notify_error(str(e), "CRITICAL")
        finally:
            await self.shutdown()

    async def _analysis_loop(self):
        """15분 주기 시장 분석 + 신호 기반 진입"""
        while self._running:
            try:
                # PAUSED 상태면 분석만 하고 진입하지 않음
                is_paused = self._is_paused()

                # 시장 분석
                signal = await self._analyzer.analyze()

                # 신호에 따른 진입 (PAUSED가 아닐 때만)
                if not is_paused and signal.signal_type in (SignalType.LONG, SignalType.SHORT):
                    trade = await self._executor.execute_entry(signal)
                    if trade:
                        logger.info(f"📌 새 포지션 생성: #{trade.id}")
                        # Discord 알림
                        await self._notifier.notify_entry(
                            side=trade.side.value,
                            entry_price=trade.entry_price,
                            quantity=trade.quantity,
                            leverage=trade.leverage,
                            stop_loss=trade.stop_loss or 0,
                            take_profit=trade.take_profit or 0,
                        )
                elif is_paused:
                    logger.info("⏸️ PAUSED — 신규 진입 차단")

                # 포지션이 있으면 청산 신호 확인
                open_trades = TradeRepository.get_open_trades()
                for trade_data in open_trades:
                    side = trade_data.get("side", "")
                    exit_signal = await self._analyzer.check_exit_signal(side)
                    if exit_signal.signal_type in (SignalType.CLOSE_LONG, SignalType.CLOSE_SHORT):
                        trade_obj = Trade(**{
                            k: v for k, v in trade_data.items()
                            if k in Trade.__fields__
                        })
                        reason = exit_signal.reasons[0] if exit_signal.reasons else "reversal"
                        await self._executor.execute_exit(trade_obj, f"signal: {reason}", 100)

                        # Discord 청산 알림
                        pnl = float(trade_data.get("pnl", 0) or 0)
                        pnl_pct = float(trade_data.get("pnl_percent", 0) or 0)
                        await self._notifier.notify_exit(
                            side=side,
                            entry_price=float(trade_data.get("entry_price", 0)),
                            exit_price=self._data_fetcher.current_price,
                            pnl=pnl,
                            pnl_percent=pnl_pct,
                            reason=reason,
                        )

            except Exception as e:
                logger.error(f"분석 루프 오류: {e}")
                self._risk.record_api_error()
                await self._notifier.notify_error(str(e))

            await asyncio.sleep(ANALYSIS_INTERVAL)

    async def _position_monitor_loop(self):
        """1분 주기 포지션 모니터링 (SL/TP/트레일링)"""
        while self._running:
            try:
                current_price = self._data_fetcher.current_price
                if current_price and current_price > 0:
                    await self._position_mgr.monitor_positions(current_price)
            except Exception as e:
                logger.error(f"포지션 모니터링 오류: {e}")

            await asyncio.sleep(POSITION_CHECK_INTERVAL)

    async def _heartbeat_loop(self):
        """5분 주기 하트비트"""
        while self._running:
            try:
                BotStatusRepository.heartbeat()

                positions = await self._exchange.get_positions()
                if positions:
                    BotStatusRepository.update_position(positions[0])
                else:
                    BotStatusRepository.update_position(None)

            except Exception as e:
                logger.error(f"하트비트 오류: {e}")

            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def shutdown(self):
        """봇 종료"""
        self._running = False
        logger.info("봇 종료 중...")

        BotStatusRepository.update_status(status=BotState.STOPPED)

        if self._ws_client:
            await self._ws_client.stop()
        if self._data_fetcher:
            await self._data_fetcher.close()
        if self._exchange:
            await self._exchange.close()

        logger.info("✅ 봇 종료 완료")
