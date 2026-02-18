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
from src.config.constants import (
    TAKE_PROFIT_LEVELS,
    TRAILING_STOP_PERCENT,
    SCALE_IN_MAX_SIZE_RATIO_PER_ADD,
    get_active_symbol,
    get_quote_currency,
)
from src.discord_bot.notifier import get_notifier
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

        desired_side = "long" if signal.signal_type == SignalType.LONG else "short"
        side = "buy" if desired_side == "long" else "sell"
        trade_side = TradeSide.LONG if desired_side == "long" else TradeSide.SHORT

        exchange_positions = await self._exchange.get_positions()
        open_position = exchange_positions[0] if exchange_positions else None
        open_trade_data = self._find_open_trade_for_side(desired_side)
        current_scale_in_count = self._extract_scale_in_count(open_trade_data)

        # 거래 가능 여부 확인
        check = await self._risk.can_trade(
            desired_side=desired_side,
            allow_scale_in=open_position is not None,
            current_scale_in_count=current_scale_in_count,
            signal_confidence=signal.confidence,
        )
        if not check["allowed"]:
            logger.warning(f"거래 불가: {check['reasons']}")
            return None

        is_scale_in = (
            open_position is not None and
            str(open_position.get("side", "")).lower() == desired_side
        )

        # 잔고 조회
        balance = await self._exchange.get_balance()
        if balance["free"] <= 0:
            logger.warning("사용 가능한 잔고 없음")
            return None

        # 포지션 사이징 (신뢰도 기반 동적 리스크)
        position = self._risk.calculate_position_size(
            balance=balance["free"],
            entry_price=signal.entry_price,
            stop_loss_price=signal.stop_loss,
            confidence=signal.confidence,
        )

        if position["size_btc"] <= 0:
            logger.warning("포지션 크기가 0")
            return None

        amount = round_quantity(position["size_btc"])
        if is_scale_in and open_position:
            current_size = float(open_position.get("size") or 0)
            max_add_size = round_quantity(current_size * SCALE_IN_MAX_SIZE_RATIO_PER_ADD)
            if max_add_size <= 0:
                logger.warning("추가 진입 한도 계산 실패")
                return None
            if amount > max_add_size:
                logger.info(
                    f"추가 진입 수량 제한 적용: {amount:.6f} → {max_add_size:.6f} BTC "
                    f"(현재 포지션의 {SCALE_IN_MAX_SIZE_RATIO_PER_ADD:.0%})"
                )
                amount = max_add_size

        try:
            # 레버리지 설정
            leverage = self._risk.select_leverage(
                volatility=0,  # MarketAnalyzer에서 전달 예정
                avg_volatility=1,
            )
            await self._exchange.set_leverage(leverage)
            await self._exchange.set_margin_mode("isolated")

            # 주문 실행 (TP/SL 포함)
            order = await self._exchange.place_market_order(
                side=side,
                amount=amount,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit_1,
            )

            # entry_price가 0이면 signal.entry_price 사용
            entry_price = order.get("price") or signal.entry_price
            filled_amount = order.get("amount") or amount

            # DB 업데이트 (신규 진입 / 추가 진입)
            if is_scale_in:
                if open_trade_data:
                    trade = self._update_trade_for_scale_in(
                        open_trade_data=open_trade_data,
                        signal=signal,
                        entry_price=entry_price,
                        filled_amount=filled_amount,
                        leverage=leverage,
                        risk_rate=position.get("risk_rate", 0.05),
                    )
                else:
                    trade = self._create_trade_for_scale_in_recovery(
                        trade_side=trade_side,
                        open_position=open_position or {},
                        signal=signal,
                        entry_price=entry_price,
                        filled_amount=filled_amount,
                        leverage=leverage,
                        risk_rate=position.get("risk_rate", 0.05),
                    )
            else:
                trade = Trade(
                    symbol=get_active_symbol(),
                    side=trade_side,
                    entry_price=entry_price,
                    quantity=filled_amount,
                    leverage=leverage,
                    stop_loss=round_price(signal.stop_loss),
                    take_profit=round_price(signal.take_profit_1) if signal.take_profit_1 else None,
                    status=TradeStatus.OPEN,
                    entry_reason={
                        "signal_type": signal.signal_type.value,
                        "confidence": signal.confidence,
                        "risk_rate": position.get("risk_rate", 0.05),
                        "reasons": signal.reasons[:5],  # 상위 5개
                        "mandatory_met": signal.mandatory_met,
                        "additional_met": signal.additional_met,
                        "entry_mode": "new",
                        "scale_in_count": 0,
                    },
                    entry_time=kst_now(),
                )
                trade = TradeRepository.save_trade(trade)

            # 성공적인 거래 후 API 에러 카운터 리셋
            self._risk.reset_api_errors()

            logger.info(
                f"{'🟢 롱' if trade_side == TradeSide.LONG else '🔴 숏'} "
                f"{'추가 진입' if is_scale_in else '진입'} 완료 | "
                f"#{trade.id} @ {entry_price:,.2f} | "
                f"SL: {signal.stop_loss:,.2f} | TP1: {signal.take_profit_1:,.2f}"
            )

            # Discord 알림 (여기서 직접 전송하여 파싱 오류 시에도 알림 보장)
            try:
                notifier = get_notifier()
                if notifier.is_ready:
                    # signal_info 구성 (AI 분석용)
                    signal_info = {
                        "signal_type": signal.signal_type.value,
                        "confidence": signal.confidence,
                        "mandatory_met": signal.mandatory_met,
                        "additional_met": signal.additional_met,
                        "reasons": signal.reasons,
                        "entry_mode": "scale_in" if is_scale_in else "new",
                        "scale_in_count": self._extract_scale_in_count(
                            trade.model_dump() if hasattr(trade, "model_dump") else None
                        ),
                    }
                    await notifier.notify_entry(
                        side=trade_side.value,
                        entry_price=entry_price,
                        quantity=filled_amount,
                        leverage=leverage,
                        stop_loss=signal.stop_loss,
                        take_profit=signal.take_profit_1 or 0,
                        signal_info=signal_info,
                    )
            except Exception as notify_err:
                logger.warning(f"진입 알림 전송 실패: {notify_err}")

            return trade

        except Exception as e:
            logger.error(f"진입 주문 실패: {e}")
            self._risk.record_api_error(str(e))
            return None

    @staticmethod
    def _extract_scale_in_count(trade_data: Optional[Dict[str, Any]]) -> int:
        if not trade_data:
            return 0
        entry_reason = trade_data.get("entry_reason", {})
        if not isinstance(entry_reason, dict):
            return 0
        try:
            return int(entry_reason.get("scale_in_count", 0) or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _find_open_trade_for_side(side: str) -> Optional[Dict[str, Any]]:
        open_trades = TradeRepository.get_open_trades()
        for trade_data in open_trades:
            if str(trade_data.get("side", "")).lower() == side:
                return trade_data
        return None

    def _update_trade_for_scale_in(
        self,
        open_trade_data: Dict[str, Any],
        signal: Signal,
        entry_price: float,
        filled_amount: float,
        leverage: int,
        risk_rate: float,
    ) -> Trade:
        trade_id = int(open_trade_data["id"])
        prev_quantity = float(open_trade_data.get("quantity") or 0)
        prev_entry_price = float(open_trade_data.get("entry_price") or entry_price)
        new_quantity = prev_quantity + filled_amount

        if new_quantity <= 0:
            weighted_entry_price = entry_price
        else:
            weighted_entry_price = (
                (prev_entry_price * prev_quantity) + (entry_price * filled_amount)
            ) / new_quantity

        prev_reason = open_trade_data.get("entry_reason", {})
        if not isinstance(prev_reason, dict):
            prev_reason = {}

        scale_in_count = self._extract_scale_in_count(open_trade_data) + 1
        scale_in_history = prev_reason.get("scale_in_history", [])
        if not isinstance(scale_in_history, list):
            scale_in_history = []
        scale_in_history.append({
            "time": kst_now().isoformat(),
            "price": round(entry_price, 2),
            "quantity": round(filled_amount, 6),
            "confidence": round(signal.confidence, 4),
        })

        updated_reason = {
            **prev_reason,
            "signal_type": signal.signal_type.value,
            "confidence": signal.confidence,
            "risk_rate": risk_rate,
            "mandatory_met": signal.mandatory_met,
            "additional_met": signal.additional_met,
            "reasons": signal.reasons[:5],
            "entry_mode": "scale_in",
            "scale_in_count": scale_in_count,
            "scale_in_history": scale_in_history[-10:],
            "last_scale_in_at": kst_now().isoformat(),
        }

        TradeRepository.update_trade(trade_id, {
            "entry_price": round_price(weighted_entry_price),
            "quantity": new_quantity,
            "leverage": leverage,
            "stop_loss": round_price(signal.stop_loss) if signal.stop_loss else None,
            "take_profit": round_price(signal.take_profit_1) if signal.take_profit_1 else None,
            "entry_reason": updated_reason,
        })

        return Trade(
            id=trade_id,
            symbol=open_trade_data.get("symbol", get_active_symbol()),
            side=TradeSide(str(open_trade_data.get("side", "long")).lower()),
            entry_price=round_price(weighted_entry_price),
            quantity=new_quantity,
            leverage=leverage,
            stop_loss=round_price(signal.stop_loss) if signal.stop_loss else None,
            take_profit=round_price(signal.take_profit_1) if signal.take_profit_1 else None,
            status=TradeStatus.OPEN,
            entry_reason=updated_reason,
            entry_time=open_trade_data.get("entry_time", kst_now()),
        )

    def _create_trade_for_scale_in_recovery(
        self,
        trade_side: TradeSide,
        open_position: Dict[str, Any],
        signal: Signal,
        entry_price: float,
        filled_amount: float,
        leverage: int,
        risk_rate: float,
    ) -> Trade:
        prev_quantity = float(open_position.get("size") or 0)
        prev_entry_price = float(open_position.get("entry_price") or entry_price)
        total_quantity = prev_quantity + filled_amount

        if total_quantity <= 0:
            weighted_entry_price = entry_price
        else:
            weighted_entry_price = (
                (prev_entry_price * prev_quantity) + (entry_price * filled_amount)
            ) / total_quantity

        trade = Trade(
            symbol=get_active_symbol(),
            side=trade_side,
            entry_price=round_price(weighted_entry_price),
            quantity=total_quantity,
            leverage=int(open_position.get("leverage") or leverage),
            stop_loss=round_price(signal.stop_loss) if signal.stop_loss else None,
            take_profit=round_price(signal.take_profit_1) if signal.take_profit_1 else None,
            status=TradeStatus.OPEN,
            entry_reason={
                "signal_type": signal.signal_type.value,
                "confidence": signal.confidence,
                "risk_rate": risk_rate,
                "reasons": signal.reasons[:5],
                "mandatory_met": signal.mandatory_met,
                "additional_met": signal.additional_met,
                "entry_mode": "scale_in_recovery",
                "scale_in_count": 1,
                "reconciled": True,
            },
            entry_time=kst_now(),
        )
        trade = TradeRepository.save_trade(trade)

        logger.warning(
            "거래소 포지션은 있으나 DB open trade가 없어 복구 생성 후 추가 진입 반영"
        )
        return trade

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
                # 성공적인 청산 후 API 에러 카운터 리셋
                self._risk.reset_api_errors()

                emoji = "💰" if pnl > 0 else "💸"
                logger.info(
                    f"{emoji} 청산 완료 | #{trade.id} {reason} | "
                    f"PnL: {pnl:+,.2f} {get_quote_currency()} ({pnl_pct:+.2f}%)"
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
            self._risk.record_api_error(str(e))
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

        중복 실행 방지: tp_levels_executed 필드로 이미 실행된 레벨 추적
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

        # 이미 실행된 TP 레벨 확인
        executed_levels = trade.tp_levels_executed or []

        for level, config in TAKE_PROFIT_LEVELS.items():
            # 이미 실행된 레벨은 스킵
            if level in executed_levels:
                continue

            if rr_ratio >= config["rr_ratio"]:
                action = config["action"]

                if action == "close_remaining" and rr_ratio >= 4.0:
                    await self.execute_exit(trade, f"TP{level} (R:R {rr_ratio:.1f})", 100)
                    return f"tp{level}_full_close"

                elif action == "activate_trailing" and rr_ratio >= 2.5 and trade.quantity > 0:
                    await self.execute_exit(trade, f"TP{level} (R:R {rr_ratio:.1f})", 30)
                    # 실행된 TP 레벨 기록
                    executed_levels.append(level)
                    TradeRepository.update_trade(trade.id, {
                        "tp_levels_executed": executed_levels,
                    })
                    return f"tp{level}_partial_trailing"

                elif action == "move_sl_to_entry" and rr_ratio >= 1.5:
                    await self.execute_exit(trade, f"TP{level} (R:R {rr_ratio:.1f})", 50)
                    # 손절을 본전으로 이동 + 실행된 TP 레벨 기록
                    executed_levels.append(level)
                    TradeRepository.update_trade(trade.id, {
                        "stop_loss": trade.entry_price,
                        "tp_levels_executed": executed_levels,
                    })
                    return f"tp{level}_breakeven"

        return None
