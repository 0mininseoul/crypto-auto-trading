"""
헬퍼 유틸리티 함수
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_DOWN
from typing import Optional, Union

# KST (한국 표준시, UTC+9)
KST = timezone(timedelta(hours=9))


def kst_now() -> datetime:
    """현재 KST 시각 반환"""
    return datetime.now(KST)


def utc_now() -> datetime:
    """현재 UTC 시각 반환 (하위 호환)"""
    return datetime.now(timezone.utc)


def timestamp_to_datetime(ts: Union[int, float]) -> datetime:
    """밀리초 타임스탬프를 KST datetime으로 변환"""
    if ts > 1e12:
        ts = ts / 1000  # 밀리초 → 초
    return datetime.fromtimestamp(ts, tz=KST)


def datetime_to_timestamp(dt: datetime) -> int:
    """datetime을 밀리초 타임스탬프로 변환"""
    return int(dt.timestamp() * 1000)


def round_price(price: float, decimals: int = 2) -> float:
    """가격 반올림 (BTC 기준 소수점 2자리)"""
    return float(Decimal(str(price)).quantize(
        Decimal(10) ** -decimals, rounding=ROUND_DOWN
    ))


def round_quantity(qty: float, decimals: int = 6) -> float:
    """수량 반올림"""
    return float(Decimal(str(qty)).quantize(
        Decimal(10) ** -decimals, rounding=ROUND_DOWN
    ))


def calculate_pnl_percent(entry_price: float, exit_price: float, side: str) -> float:
    """
    PnL 퍼센트 계산 (레버리지 미적용)

    Args:
        entry_price: 진입가
        exit_price: 청산가
        side: 'long' 또는 'short'

    Returns:
        수익률 (%)
    """
    if side == "long":
        return ((exit_price - entry_price) / entry_price) * 100
    else:  # short
        return ((entry_price - exit_price) / entry_price) * 100


def format_usdt(amount: float) -> str:
    """USDT 금액 포맷팅"""
    return f"${amount:,.2f}"


def format_btc(amount: float) -> str:
    """BTC 수량 포맷팅"""
    return f"{amount:.6f} BTC"


def format_percent(value: float) -> str:
    """퍼센트 포맷팅"""
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"
