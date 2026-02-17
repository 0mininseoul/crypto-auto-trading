"""
포지션 관리 (Position Manager)
포지션 모니터링, 손절/익절 실행, 트레일링 스탑
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from src.exchange.bitget_client import BitgetClient
from src.core.order_executor import OrderExecutor
from src.core.risk_manager import RiskManager
from src.database.repository import TradeRepository, BotStatusRepository
from src.database.models import Trade, TradeSide, TradeStatus
from src.config.constants import TRAILING_STOP_PERCENT, FLASH_CRASH_PERCENT
from src.discord_bot.notifier import get_notifier
from src.utils.logger import setup_logger
from src.utils.helpers import format_usdt, format_percent

logger = setup_logger("position_manager")


class PositionManager:
    """포지션 관리"""

    def __init__(
        self,
        exchange: BitgetClient,
        order_executor: OrderExecutor,
        risk_manager: RiskManager,
    ):
        self._exchange = exchange
        self._executor = order_executor
        self._risk = risk_manager
        self._notifier = get_notifier()
        self._trailing_active: Dict[int, bool] = {}      # trade_id → 활성 여부
        self._trailing_stop: Dict[int, float] = {}        # trade_id → 트레일링 스탑가
        self._highest_price: Dict[int, float] = {}        # trade_id → 최고가 (롱)
        self._lowest_price: Dict[int, float] = {}         # trade_id → 최저가 (숏)
        self._prev_price: float = 0                       # 이전 가격 (Flash Crash 감지)

    async def monitor_positions(self, current_price: float):
        """
        포지션 모니터링 (1분 주기 호출)

        1. 손절 확인
        2. 단계별 익절 확인
        3. 트레일링 스탑 업데이트
        4. Flash Crash 감지
        """
        # Flash crash 체크
        if self._prev_price > 0:
            price_change_pct = abs(current_price - self._prev_price) / self._prev_price * 100
            if price_change_pct >= FLASH_CRASH_PERCENT:
                logger.critical(f"🚨 Flash {'Crash' if current_price < self._prev_price else 'Pump'}: {price_change_pct:.1f}%")
                await self._risk.emergency_stop(f"Flash event: {price_change_pct:.1f}%")
                return
        self._prev_price = current_price

        # 열려있는 거래 조회
        open_trades = TradeRepository.get_open_trades()
        if not open_trades:
            return

        for trade_data in open_trades:
            trade = Trade(**{
                k: v for k, v in trade_data.items()
                if k in Trade.__fields__
            })

            await self._check_single_position(trade, current_price)

    async def _check_single_position(self, trade: Trade, current_price: float):
        """개별 포지션 모니터링"""
        trade_id = trade.id

        # === 1. 손절 확인 ===
        if trade.stop_loss:
            hit_sl = (
                (trade.side == TradeSide.LONG and current_price <= trade.stop_loss) or
                (trade.side == TradeSide.SHORT and current_price >= trade.stop_loss)
            )
            if hit_sl:
                logger.warning(f"🛑 손절 도달 | #{trade_id} @ {current_price:,.2f}")
                success = await self._executor.execute_exit(trade, "stop_loss", 100)
                if success:
                    # Discord 손절 알림
                    pnl, pnl_pct = self._calculate_pnl(trade, current_price)
                    await self._notifier.notify_stop_loss(
                        side=trade.side.value,
                        entry_price=trade.entry_price,
                        exit_price=current_price,
                        loss=abs(pnl),
                        loss_percent=abs(pnl_pct),
                    )
                self._cleanup_tracking(trade_id)
                return

        # === 2. 트레일링 스탑 ===
        if self._trailing_active.get(trade_id, False):
            hit_trailing = await self._update_trailing_stop(trade, current_price)
            if hit_trailing:
                return

        # === 3. 단계별 익절 ===
        result = await self._executor.check_take_profit_levels(trade, current_price)
        if result:
            pnl, pnl_pct = self._calculate_pnl(trade, current_price)

            if "breakeven" in result:
                logger.info(f"📌 손절 → 본전으로 이동 | #{trade_id}")
                # TP1 부분 익절 알림
                await self._notifier.notify_exit(
                    side=trade.side.value,
                    entry_price=trade.entry_price,
                    exit_price=current_price,
                    pnl=pnl * 0.5,  # 50% 청산
                    pnl_percent=pnl_pct,
                    reason="TP1 (50% 부분익절, SL→본전)",
                )
            elif "trailing" in result or "partial" in result:
                self._trailing_active[trade_id] = True
                if trade.side == TradeSide.LONG:
                    self._highest_price[trade_id] = current_price
                    self._trailing_stop[trade_id] = current_price * (1 - TRAILING_STOP_PERCENT / 100)
                else:
                    self._lowest_price[trade_id] = current_price
                    self._trailing_stop[trade_id] = current_price * (1 + TRAILING_STOP_PERCENT / 100)
                logger.info(f"📈 트레일링 스탑 활성화 | #{trade_id} @ {self._trailing_stop[trade_id]:,.2f}")
                # TP2 부분 익절 알림
                await self._notifier.notify_exit(
                    side=trade.side.value,
                    entry_price=trade.entry_price,
                    exit_price=current_price,
                    pnl=pnl * 0.3,  # 30% 청산
                    pnl_percent=pnl_pct,
                    reason="TP2 (30% 부분익절, 트레일링 활성화)",
                )
            elif "full_close" in result:
                # TP3 전량 청산 알림
                await self._notifier.notify_exit(
                    side=trade.side.value,
                    entry_price=trade.entry_price,
                    exit_price=current_price,
                    pnl=pnl,
                    pnl_percent=pnl_pct,
                    reason="TP3 (전량 익절)",
                )
                self._cleanup_tracking(trade_id)

    async def _update_trailing_stop(self, trade: Trade, current_price: float) -> bool:
        """트레일링 스탑 업데이트"""
        trade_id = trade.id

        if trade.side == TradeSide.LONG:
            # 최고가 갱신
            prev_high = self._highest_price.get(trade_id, current_price)
            if current_price > prev_high:
                self._highest_price[trade_id] = current_price
                new_trailing = current_price * (1 - TRAILING_STOP_PERCENT / 100)
                self._trailing_stop[trade_id] = new_trailing

            # 트레일링 도달
            if current_price <= self._trailing_stop.get(trade_id, 0):
                logger.info(f"📉 트레일링 스탑 도달 | #{trade_id} @ {current_price:,.2f}")
                success = await self._executor.execute_exit(trade, "trailing_stop", 100)
                if success:
                    # Discord 트레일링 청산 알림
                    pnl, pnl_pct = self._calculate_pnl(trade, current_price)
                    await self._notifier.notify_exit(
                        side=trade.side.value,
                        entry_price=trade.entry_price,
                        exit_price=current_price,
                        pnl=pnl,
                        pnl_percent=pnl_pct,
                        reason="트레일링 스탑",
                    )
                self._cleanup_tracking(trade_id)
                return True

        elif trade.side == TradeSide.SHORT:
            prev_low = self._lowest_price.get(trade_id, current_price)
            if current_price < prev_low:
                self._lowest_price[trade_id] = current_price
                new_trailing = current_price * (1 + TRAILING_STOP_PERCENT / 100)
                self._trailing_stop[trade_id] = new_trailing

            if current_price >= self._trailing_stop.get(trade_id, float("inf")):
                logger.info(f"📈 트레일링 스탑 도달 | #{trade_id} @ {current_price:,.2f}")
                success = await self._executor.execute_exit(trade, "trailing_stop", 100)
                if success:
                    # Discord 트레일링 청산 알림
                    pnl, pnl_pct = self._calculate_pnl(trade, current_price)
                    await self._notifier.notify_exit(
                        side=trade.side.value,
                        entry_price=trade.entry_price,
                        exit_price=current_price,
                        pnl=pnl,
                        pnl_percent=pnl_pct,
                        reason="트레일링 스탑",
                    )
                self._cleanup_tracking(trade_id)
                return True

        return False

    def _cleanup_tracking(self, trade_id: int):
        """거래 추적 데이터 정리"""
        self._trailing_active.pop(trade_id, None)
        self._trailing_stop.pop(trade_id, None)
        self._highest_price.pop(trade_id, None)
        self._lowest_price.pop(trade_id, None)

    def _calculate_pnl(self, trade: Trade, exit_price: float) -> tuple[float, float]:
        """PnL 계산"""
        if trade.side == TradeSide.LONG:
            pnl = (exit_price - trade.entry_price) * trade.quantity
            pnl_pct = (exit_price - trade.entry_price) / trade.entry_price * 100
        else:
            pnl = (trade.entry_price - exit_price) * trade.quantity
            pnl_pct = (trade.entry_price - exit_price) / trade.entry_price * 100
        return pnl, pnl_pct
