"""
주문 실행 엔진 (Order Executor)
진입/청산 주문 + 부분 익절 + 트레일링 스탑
"""
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from src.utils.helpers import kst_now

from src.exchange.bitget_client import BitgetClient
from src.core.risk_manager import RiskManager
from src.database.repository import TradeRepository
from src.database.models import Trade, TradeSide, TradeStatus
from src.indicators.signals import Signal, SignalType
from src.config.constants import TAKE_PROFIT_LEVELS, TRAILING_STOP_PERCENT, CCXT_SYMBOL
from src.utils.logger import setup_logger
from src.utils.helpers import round_price, round_quantity

logger = setup_logger("order_executor")


class OrderExecutor:
    """주문 실행"""

    def __init__(self, exchange: BitgetClient, risk_manager: RiskManager):
        self._exchange = exchange
        self._risk = risk_manager

    async def execute_entry(self, signal: Signal) -> Optional[Trade]:
        """
        진입 주문 실행

        Args:
            signal: 매매 신호

        Returns:
            Trade 객체 또는 None
        """
        if signal.signal_type not in (SignalType.LONG, SignalType.SHORT):
            return None

        # 거래 가능 여부 확인
        check = await self._risk.can_trade()
        if not check["allowed"]:
            logger.warning(f"거래 불가: {check['reasons']}")
            return None

        # 잔고 조회
        balance = await self._exchange.get_balance()
        if balance["free"] <= 0:
            logger.warning("사용 가능한 잔고 없음")
            return None

        side = "buy" if signal.signal_type == SignalType.LONG else "sell"
        trade_side = TradeSide.LONG if signal.signal_type == SignalType.LONG else TradeSide.SHORT

        # 포지션 사이징
        position = self._risk.calculate_position_size(
            balance=balance["free"],
            entry_price=signal.entry_price,
            stop_loss_price=signal.stop_loss,
        )

        if position["size_btc"] <= 0:
            logger.warning("포지션 크기가 0")
            return None

        amount = round_quantity(position["size_btc"])

        try:
            # 레버리지 설정
            leverage = self._risk.select_leverage(
                volatility=0,  # MarketAnalyzer에서 전달 예정
                avg_volatility=1,
            )
            await self._exchange.set_leverage(leverage)
            await self._exchange.set_margin_mode("isolated")

            # 주문 실행
            order = await self._exchange.place_market_order(side, amount)

            entry_price = order.get("price", signal.entry_price)

            # DB에 거래 기록
            trade = Trade(
                symbol="BTCUSDT",
                side=trade_side,
                entry_price=entry_price,
                quantity=order.get("amount", amount),
                leverage=leverage,
                stop_loss=round_price(signal.stop_loss),
                take_profit=round_price(signal.take_profit_1) if signal.take_profit_1 else None,
                status=TradeStatus.OPEN,
                entry_reason={
                    "signal_type": signal.signal_type.value,
                    "confidence": signal.confidence,
                    "reasons": signal.reasons[:5],  # 상위 5개
                    "mandatory_met": signal.mandatory_met,
                    "additional_met": signal.additional_met,
                },
                entry_time=kst_now(),
            )
            trade = TradeRepository.save_trade(trade)

            logger.info(
                f"{'🟢 롱' if trade_side == TradeSide.LONG else '🔴 숏'} 진입 완료 | "
                f"#{trade.id} @ {entry_price:,.2f} | "
                f"SL: {signal.stop_loss:,.2f} | TP1: {signal.take_profit_1:,.2f}"
            )

            return trade

        except Exception as e:
            logger.error(f"진입 주문 실패: {e}")
            self._risk.record_api_error()
            return None

    async def execute_exit(
        self,
        trade: Trade,
        reason: str,
        partial_percent: float = 100,
    ) -> bool:
        """
        청산 주문 실행

        Args:
            trade: 열린 거래
            reason: 청산 사유
            partial_percent: 부분 청산 비율 (%)

        Returns:
            성공 여부
        """
        try:
            close_amount = trade.quantity * (partial_percent / 100)
            close_amount = round_quantity(close_amount)

            order = await self._exchange.close_position(
                side=trade.side.value,
                amount=close_amount,
            )

            exit_price = order.get("price", 0)

            if partial_percent >= 100:
                # 전량 청산
                pnl_pct = (
                    ((exit_price - trade.entry_price) / trade.entry_price * 100)
                    if trade.side == TradeSide.LONG
                    else ((trade.entry_price - exit_price) / trade.entry_price * 100)
                )
                pnl = (exit_price - trade.entry_price) * trade.quantity if trade.side == TradeSide.LONG \
                    else (trade.entry_price - exit_price) * trade.quantity

                TradeRepository.update_trade(trade.id, {
                    "status": TradeStatus.CLOSED.value,
                    "exit_price": exit_price,
                    "exit_time": kst_now().isoformat(),
                    "exit_reason": reason,
                    "pnl": pnl,
                    "pnl_percent": round(pnl_pct, 2),
                })

                self._risk.record_trade_result(pnl)

                emoji = "💰" if pnl > 0 else "💸"
                logger.info(
                    f"{emoji} 청산 완료 | #{trade.id} {reason} | "
                    f"PnL: {pnl:+,.2f} USDT ({pnl_pct:+.2f}%)"
                )
            else:
                # 부분 청산 (수량 업데이트)
                remaining = trade.quantity - close_amount
                TradeRepository.update_trade(trade.id, {
                    "quantity": remaining,
                })
                logger.info(
                    f"📌 부분 청산 ({partial_percent}%) | #{trade.id} | "
                    f"잔여: {remaining:.6f} BTC"
                )

            return True

        except Exception as e:
            logger.error(f"청산 주문 실패: {e}")
            self._risk.record_api_error()
            return False

    async def check_take_profit_levels(
        self,
        trade: Trade,
        current_price: float,
    ) -> Optional[str]:
        """
        단계별 익절 확인 및 실행

        TP1 (R:R 1.5:1) → 50% 청산, SL을 본전으로
        TP2 (R:R 2.5:1) → 30% 청산, 트레일링 활성화
        TP3 (R:R 4.0:1) → 잔여 전량 청산
        """
        if not trade.stop_loss:
            return None

        risk = abs(trade.entry_price - trade.stop_loss)
        if risk == 0:
            return None

        if trade.side == TradeSide.LONG:
            rr_ratio = (current_price - trade.entry_price) / risk
        else:
            rr_ratio = (trade.entry_price - current_price) / risk

        for level, config in TAKE_PROFIT_LEVELS.items():
            if rr_ratio >= config["rr_ratio"]:
                action = config["action"]

                if action == "close_remaining" and rr_ratio >= 4.0:
                    await self.execute_exit(trade, f"TP{level} (R:R {rr_ratio:.1f})", 100)
                    return f"tp{level}_full_close"

                elif action == "activate_trailing" and rr_ratio >= 2.5 and trade.quantity > 0:
                    await self.execute_exit(trade, f"TP{level} (R:R {rr_ratio:.1f})", 30)
                    return f"tp{level}_partial"

                elif action == "move_sl_to_entry" and rr_ratio >= 1.5:
                    await self.execute_exit(trade, f"TP{level} (R:R {rr_ratio:.1f})", 50)
                    # 손절을 본전으로 이동
                    TradeRepository.update_trade(trade.id, {
                        "stop_loss": trade.entry_price,
                    })
                    return f"tp{level}_breakeven"

        return None
