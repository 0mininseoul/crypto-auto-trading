"""
리스크 관리 엔진 (Risk Manager)
포지션 사이징, 손실 한도, 거래 제한, 긴급 중단
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from src.exchange.bitget_client import BitgetClient
from src.database.repository import TradeRepository, BotStatusRepository
from src.database.models import BotState
from src.config.constants import (
    RISK_PER_TRADE,
    DAILY_MAX_LOSS,
    WEEKLY_MAX_LOSS,
    MAX_CONCURRENT_POSITIONS,
    MAX_DAILY_TRADES,
    CONSECUTIVE_LOSS_COOLDOWN,
    DEFAULT_LEVERAGE,
    LOW_VOLATILITY_LEVERAGE,
    HIGH_VOLATILITY_LEVERAGE,
    MAX_STOP_LOSS_PERCENT,
    FLASH_CRASH_PERCENT,
    API_ERROR_STREAK_LIMIT,
    MIN_ORDER_SIZE_USDT,
)
from src.utils.logger import setup_logger
from src.utils.helpers import format_usdt, format_percent, kst_now

logger = setup_logger("risk_manager")


# API 오류 자동 복구 시간 (1시간)
API_ERROR_RESET_HOURS = 1


class RiskManager:
    """리스크 관리"""

    def __init__(self, exchange: BitgetClient):
        self._exchange = exchange
        self._api_error_count = 0
        self._last_api_error_time: Optional[datetime] = None
        self._consecutive_losses = 0
        self._last_loss_time: Optional[datetime] = None

    async def can_trade(self) -> Dict[str, Any]:
        """
        거래 가능 여부 종합 판단

        Returns:
            {"allowed": bool, "reasons": [...]}
        """
        reasons = []

        # 1. 동시 포지션 제한
        if await self._exchange.has_open_position():
            reasons.append(f"이미 포지션 보유 중 (최대 {MAX_CONCURRENT_POSITIONS}개)")

        # 2. 일일 거래 횟수
        today_count = TradeRepository.get_today_trade_count()
        if today_count >= MAX_DAILY_TRADES:
            reasons.append(f"일일 최대 거래 횟수 도달 ({today_count}/{MAX_DAILY_TRADES})")

        # 3. 일일 손실 한도
        balance = await self._exchange.get_balance()
        total_balance = balance["total"]
        if total_balance > 0:
            today_pnl = TradeRepository.get_today_pnl()
            daily_loss_pct = abs(min(0, today_pnl)) / total_balance
            if daily_loss_pct >= DAILY_MAX_LOSS:
                reasons.append(f"일일 최대 손실 도달 ({format_percent(-daily_loss_pct * 100)})")

        # 4. 연속 손절 쿨다운
        if self._consecutive_losses >= CONSECUTIVE_LOSS_COOLDOWN["losses"]:
            cooldown_hours = CONSECUTIVE_LOSS_COOLDOWN["cooldown_hours"]
            if self._last_loss_time:
                elapsed = kst_now() - self._last_loss_time
                if elapsed < timedelta(hours=cooldown_hours):
                    remaining = cooldown_hours - elapsed.total_seconds() / 3600
                    reasons.append(f"연속 손절 쿨다운 중 ({remaining:.1f}시간 남음)")

        # 5. API 오류 연속 (자동 복구 체크)
        if self._api_error_count >= API_ERROR_STREAK_LIMIT:
            # 일정 시간 경과 후 자동 리셋
            if self._last_api_error_time:
                elapsed = kst_now() - self._last_api_error_time
                if elapsed >= timedelta(hours=API_ERROR_RESET_HOURS):
                    logger.info(
                        f"✅ API 오류 카운터 자동 리셋 "
                        f"({API_ERROR_RESET_HOURS}시간 경과)"
                    )
                    self.reset_api_errors()
                else:
                    remaining_mins = (
                        API_ERROR_RESET_HOURS * 60 - elapsed.total_seconds() / 60
                    )
                    reasons.append(
                        f"API 오류 {self._api_error_count}회 연속 발생 "
                        f"(자동 복구까지 {remaining_mins:.0f}분)"
                    )
            else:
                reasons.append(f"API 오류 {self._api_error_count}회 연속 발생")

        allowed = len(reasons) == 0
        if not allowed:
            logger.warning(f"⛔ 거래 불가: {reasons}")

        return {"allowed": allowed, "reasons": reasons}

    def calculate_position_size(
        self,
        balance: float,
        entry_price: float,
        stop_loss_price: float,
        leverage: int = DEFAULT_LEVERAGE,
    ) -> Dict[str, float]:
        """
        포지션 크기 계산

        공식: position_size = (잔고 × 리스크%) / |진입가 - 손절가|

        Args:
            balance: 계좌 잔고 (USDT)
            entry_price: 진입 예정가
            stop_loss_price: 손절가
            leverage: 레버리지

        Returns:
            {"size_btc": ..., "size_usdt": ..., "margin_required": ..., "risk_amount": ...}
        """
        risk_amount = balance * RISK_PER_TRADE
        price_diff = abs(entry_price - stop_loss_price)

        if price_diff == 0:
            logger.error("진입가와 손절가가 동일합니다")
            return {"size_btc": 0, "size_usdt": 0, "margin_required": 0, "risk_amount": 0}

        # 손절폭 제한 (최대 3%)
        sl_percent = (price_diff / entry_price) * 100
        if sl_percent > MAX_STOP_LOSS_PERCENT:
            logger.warning(f"손절폭 초과 ({sl_percent:.1f}% > {MAX_STOP_LOSS_PERCENT}%), 조정됨")
            price_diff = entry_price * (MAX_STOP_LOSS_PERCENT / 100)
            risk_amount = balance * RISK_PER_TRADE

        size_btc = risk_amount / price_diff
        size_usdt = size_btc * entry_price
        margin_required = size_usdt / leverage

        # 최소 주문 금액 검증
        if size_usdt < MIN_ORDER_SIZE_USDT:
            logger.warning(
                f"⚠️ 포지션 크기가 최소 주문 금액 미달 "
                f"({format_usdt(size_usdt)} < {format_usdt(MIN_ORDER_SIZE_USDT)})"
            )
            return {"size_btc": 0, "size_usdt": 0, "margin_required": 0, "risk_amount": 0}

        logger.info(
            f"포지션 사이징: {size_btc:.6f} BTC ({format_usdt(size_usdt)}) | "
            f"마진: {format_usdt(margin_required)} | 리스크: {format_usdt(risk_amount)}"
        )

        return {
            "size_btc": size_btc,
            "size_usdt": size_usdt,
            "margin_required": margin_required,
            "risk_amount": risk_amount,
        }

    def select_leverage(self, volatility: float, avg_volatility: float) -> int:
        """
        변동성 기반 레버리지 선택

        Args:
            volatility: 현재 변동성 (%)
            avg_volatility: 평균 변동성 (%)
        """
        if avg_volatility == 0:
            return DEFAULT_LEVERAGE

        ratio = volatility / avg_volatility

        if ratio < 0.7:
            lev = LOW_VOLATILITY_LEVERAGE
        elif ratio > 1.5:
            lev = HIGH_VOLATILITY_LEVERAGE
        else:
            lev = DEFAULT_LEVERAGE

        logger.info(f"레버리지 선택: {lev}x (변동성 비율: {ratio:.2f})")
        return lev

    def record_trade_result(self, pnl: float):
        """거래 결과 기록 (연속 손절 추적)"""
        if pnl < 0:
            self._consecutive_losses += 1
            self._last_loss_time = kst_now()
            logger.info(f"연속 손절: {self._consecutive_losses}회")
        else:
            self._consecutive_losses = 0
            logger.info("연속 손절 카운터 초기화")

    def record_api_error(self, error_msg: str = ""):
        """API 오류 기록"""
        self._api_error_count += 1
        self._last_api_error_time = kst_now()

        if self._api_error_count >= API_ERROR_STREAK_LIMIT:
            logger.critical(
                f"🚨 API 오류 {self._api_error_count}회 연속 — 거래 중단 "
                f"({API_ERROR_RESET_HOURS}시간 후 자동 복구)"
            )
            if error_msg:
                logger.critical(f"   마지막 오류: {error_msg}")

    def reset_api_errors(self):
        """API 오류 카운터 초기화"""
        if self._api_error_count > 0:
            logger.info(f"🔄 API 오류 카운터 초기화 (이전: {self._api_error_count}회)")
        self._api_error_count = 0
        self._last_api_error_time = None

    async def emergency_stop(self, reason: str):
        """
        긴급 중단: 모든 포지션 청산 + 봇 정지

        Args:
            reason: 중단 사유
        """
        logger.critical(f"🚨 긴급 중단: {reason}")

        try:
            positions = await self._exchange.get_positions()
            for pos in positions:
                await self._exchange.close_position(
                    side=pos["side"],
                    amount=pos["size"],
                )
                logger.info(f"포지션 청산: {pos['side']} {pos['size']}")
        except Exception as e:
            logger.error(f"긴급 청산 실패: {e}")

        BotStatusRepository.update_status(status=BotState.STOPPED)
