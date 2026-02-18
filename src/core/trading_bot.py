"""
메인 트레이딩 봇 (Trading Bot)
전체 거래 플로우 오케스트레이션 + Discord 알림 연동
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from src.exchange.bitget_client import BitgetClient
from src.exchange.data_fetcher import DataFetcher
from src.exchange.websocket_client import BitgetWebSocket
from src.core.market_analyzer import MarketAnalyzer
from src.core.risk_manager import RiskManager
from src.core.order_executor import OrderExecutor
from src.core.position_manager import PositionManager
from src.indicators.signals import SignalType
from src.database.repository import BotStatusRepository, TradeRepository
from src.database.models import BotState, Trade, TradeSide, TradeStatus
from src.config.constants import TIMEFRAMES, MAX_STOP_LOSS_PERCENT, get_active_symbol
from src.config.settings import get_settings
from src.discord_bot.notifier import get_notifier
from src.utils.logger import setup_logger

logger = setup_logger("trading_bot")

# 분석 주기 (초)
ANALYSIS_INTERVAL = 60 * 5       # 5분마다 신호 분석 (15분봉 데이트레이딩)
POSITION_CHECK_INTERVAL = 60     # 1분마다 포지션 모니터링
HEARTBEAT_INTERVAL = 60 * 5      # 5분마다 하트비트
POSITION_SYNC_STALE_STREAK = 3   # DB만 열린 포지션이 연속 N회 확인되면 정리


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
        self._position_mismatch_streak = 0

    def _is_paused(self) -> bool:
        """봇이 PAUSED 상태인지 DB에서 확인"""
        status = BotStatusRepository.get_status()
        if status and status.get("status") == BotState.PAUSED.value:
            return True
        return False

    async def initialize(self):
        """봇 초기화"""
        from src.config.trading_mode import get_trading_mode, is_demo_mode

        logger.info("=" * 50)
        logger.info("🤖 Bitcoin Autotrading Bot 시작")
        logger.info(f"   모드: {'🔧 데모' if is_demo_mode() else '⚠️ 라이브'}")
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

        # AI 차트 분석기 초기화
        try:
            from src.ai.chart_analyzer import init_chart_analyzer
            chart_analyzer = init_chart_analyzer(self._data_fetcher, self._exchange)
            if chart_analyzer.is_available:
                logger.info("🧠 AI 차트 분석기 활성화 (Gemini 3.0 Flash)")
            else:
                logger.warning("⚠️ AI 차트 분석기 비활성화 (GEMINI_API_KEY 미설정)")
        except Exception as e:
            logger.warning(f"AI 차트 분석기 초기화 실패: {e}")

        # 봇 상태 업데이트
        BotStatusRepository.update_status(
            status=BotState.RUNNING,
            trading_mode=get_trading_mode(),
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

                # 거래소 포지션 ↔ DB 오픈 트레이드 동기화
                await self._reconcile_exchange_and_db_positions()

                # 시장 분석
                signal = await self._analyzer.analyze()

                # 신호에 따른 진입 (PAUSED가 아닐 때만)
                if not is_paused and signal.signal_type in (SignalType.LONG, SignalType.SHORT):
                    trade = await self._executor.execute_entry(signal)
                    if trade:
                        logger.info(f"📌 새 포지션 생성: #{trade.id}")
                        # Discord 알림은 order_executor에서 직접 전송
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
                        quantity = float(trade_data.get("quantity", 0) or 0)
                        await self._notifier.notify_exit(
                            side=side,
                            entry_price=float(trade_data.get("entry_price", 0)),
                            exit_price=self._data_fetcher.current_price,
                            pnl=pnl,
                            pnl_percent=pnl_pct,
                            reason=reason,
                            quantity=quantity,
                        )

            except Exception as e:
                logger.error(f"분석 루프 오류: {e}")
                self._risk.record_api_error()
                await self._notifier.notify_error(str(e))

            # 다음 캔들 마감까지 대기 (5분 단위 정각 + 2초)
            # 예: 12:00:00 → 12:05:02에 분석 실행
            now = datetime.now(timezone.utc)
            next_timestamp = (now.timestamp() // 300 + 1) * 300  # 다음 5분 단위 시각
            sleep_duration = next_timestamp - now.timestamp() + 2  # 2초 버퍼 (데이터 수신 지연 고려)
            
            if sleep_duration < 0:
                sleep_duration = 0
            
            logger.info(f"⏳ 다음 캔들 마감 대기: {sleep_duration:.1f}초 후 분석")
            await asyncio.sleep(sleep_duration)

    async def _reconcile_exchange_and_db_positions(self):
        """
        거래소 실포지션과 DB open_trades 간 불일치 보정

        - 거래소 O / DB X: DB에 복구 생성
        - 거래소 X / DB O: 연속 확인 후 stale 거래 자동 종료 처리
        - 거래소 O / DB O: 수량/평단 드리프트 최소 보정
        """
        positions = await self._exchange.get_positions()
        open_trades = TradeRepository.get_open_trades()

        # 케이스 1) 거래소에는 있는데 DB에 없음 → 즉시 복구
        if positions and not open_trades:
            pos = positions[0]
            side_str = str(pos.get("side", "")).lower()
            if side_str not in ("long", "short"):
                logger.warning(f"포지션 복구 실패: 알 수 없는 방향 {side_str}")
                return

            entry_price = float(pos.get("entry_price") or 0)
            quantity = float(pos.get("size") or 0)
            leverage = int(pos.get("leverage") or 1)

            if entry_price <= 0 or quantity <= 0:
                logger.warning(
                    f"포지션 복구 실패: entry={entry_price}, quantity={quantity}"
                )
                return

            stop_loss = (
                entry_price * (1 - MAX_STOP_LOSS_PERCENT / 100)
                if side_str == "long"
                else entry_price * (1 + MAX_STOP_LOSS_PERCENT / 100)
            )

            recovered = Trade(
                symbol=get_active_symbol(),
                side=TradeSide(side_str),
                entry_price=entry_price,
                quantity=quantity,
                leverage=leverage,
                stop_loss=stop_loss,
                take_profit=None,
                status=TradeStatus.OPEN,
                entry_reason={
                    "source": "exchange_position_reconcile",
                    "reconciled": True,
                    "scale_in_count": 0,
                },
            )
            saved = TradeRepository.save_trade(recovered)
            self._position_mismatch_streak = 0
            logger.warning(
                f"거래소 오픈 포지션을 DB로 복구 생성: #{saved.id} {side_str} {quantity:.6f}"
            )
            return

        # 케이스 2) DB에는 있는데 거래소에 없음 → 연속 확인 후 정리
        if not positions and open_trades:
            self._position_mismatch_streak += 1
            logger.warning(
                "DB open trade는 있으나 거래소 포지션이 없음 "
                f"({self._position_mismatch_streak}/{POSITION_SYNC_STALE_STREAK})"
            )

            if self._position_mismatch_streak < POSITION_SYNC_STALE_STREAK:
                return

            current_price = float(self._data_fetcher.current_price or 0)
            for trade_data in open_trades:
                trade_id = trade_data.get("id")
                if not trade_id:
                    continue

                entry_price = float(trade_data.get("entry_price") or 0)
                quantity = float(trade_data.get("quantity") or 0)
                side = str(trade_data.get("side", "")).lower()
                exit_price = current_price if current_price > 0 else entry_price

                if entry_price <= 0 or quantity <= 0:
                    pnl = 0.0
                    pnl_pct = 0.0
                elif side == "short":
                    pnl = (entry_price - exit_price) * quantity
                    pnl_pct = (entry_price - exit_price) / entry_price * 100
                else:
                    pnl = (exit_price - entry_price) * quantity
                    pnl_pct = (exit_price - entry_price) / entry_price * 100

                TradeRepository.update_trade(int(trade_id), {
                    "status": TradeStatus.CLOSED.value,
                    "exit_price": exit_price,
                    "exit_time": datetime.now(timezone.utc).isoformat(),
                    "exit_reason": "sync:no_exchange_position",
                    "pnl": pnl,
                    "pnl_percent": round(pnl_pct, 2),
                })

            logger.warning("거래소 미존재 stale open trade 정리 완료")
            self._position_mismatch_streak = 0
            return

        self._position_mismatch_streak = 0

        # 케이스 3) 둘 다 있음 → 핵심 필드 드리프트 보정
        if positions and open_trades:
            pos = positions[0]
            side = str(pos.get("side", "")).lower()
            matching = None
            for trade_data in open_trades:
                if str(trade_data.get("side", "")).lower() == side:
                    matching = trade_data
                    break
            if matching is None:
                return

            updates: Dict[str, Any] = {}
            exchange_size = float(pos.get("size") or 0)
            db_size = float(matching.get("quantity") or 0)
            if exchange_size > 0 and abs(exchange_size - db_size) > 1e-6:
                updates["quantity"] = exchange_size

            exchange_entry = float(pos.get("entry_price") or 0)
            db_entry = float(matching.get("entry_price") or 0)
            if exchange_entry > 0 and abs(exchange_entry - db_entry) > 0.5:
                updates["entry_price"] = exchange_entry

            exchange_lev = int(pos.get("leverage") or 0)
            db_lev = int(matching.get("leverage") or 0)
            if exchange_lev > 0 and exchange_lev != db_lev:
                updates["leverage"] = exchange_lev

            if updates and matching.get("id"):
                TradeRepository.update_trade(int(matching["id"]), updates)
                logger.info(f"포지션 동기화 보정: trade#{matching['id']} {updates}")

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
