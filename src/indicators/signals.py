"""
매매 신호 생성 (Signal Generator)
TRADING_STRATEGY.md의 진입/청산 조건 구현
"""
import pandas as pd
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum

from src.indicators.trend import (
    add_all_emas,
    is_ema_bullish_alignment,
    is_ema_bearish_alignment,
    is_price_above_ema,
    is_price_below_ema,
    detect_ema_crossover,
    is_higher_low,
    is_lower_high,
    find_swing_lows,
    find_swing_highs,
)
from src.indicators.momentum import (
    add_rsi,
    add_macd,
    detect_rsi_bullish_divergence,
    detect_rsi_bearish_divergence,
    is_rsi_bounce_from_oversold,
    is_rsi_drop_from_overbought,
    detect_macd_crossover,
    is_macd_histogram_positive,
    is_macd_histogram_negative,
)
from src.indicators.volume import (
    add_volume_indicators,
    is_volume_above_average,
    is_volume_too_low,
    is_obv_trending_up,
    is_obv_trending_down,
)
from src.config.constants import MIN_RR_RATIO
from src.utils.logger import setup_logger

logger = setup_logger("signals")


class SignalType(str, Enum):
    LONG = "long"
    SHORT = "short"
    CLOSE_LONG = "close_long"
    CLOSE_SHORT = "close_short"
    NO_SIGNAL = "no_signal"


@dataclass
class Signal:
    """매매 신호"""
    signal_type: SignalType
    confidence: float = 0.0           # 신뢰도 (0.0 ~ 1.0)
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    entry_price: Optional[float] = None
    reasons: List[str] = field(default_factory=list)
    mandatory_met: int = 0             # 충족된 필수 조건 수
    additional_met: int = 0            # 충족된 추가 조건 수


def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """모든 지표가 추가된 DataFrame 반환"""
    df = df.copy()
    df = add_all_emas(df)
    df = add_rsi(df)
    df = add_macd(df)
    df = add_volume_indicators(df)
    return df


def check_long_entry(
    df_4h: pd.DataFrame,
    df_1d: Optional[pd.DataFrame] = None,
) -> Signal:
    """
    롱 포지션 진입 조건 검사

    필수 조건 (4개 모두 충족):
    1. 1일봉 EMA 50 위에 가격
    2. 4시간봉 EMA 정배열 (13 > 21 > 50)
    3. Higher Low 구조
    4. 진입 캔들 거래량 > 14MA

    추가 조건 (2개 이상 충족):
    1. RSI 상승 다이버전스
    2. RSI 30→40 반등
    3. MACD 골든크로스 또는 히스토그램 양전환
    4. OBV 상승 추세
    """
    signal = Signal(signal_type=SignalType.NO_SIGNAL)
    mandatory_count = 0
    additional_count = 0
    reasons = []

    # === 필수 조건 ===

    # 1. 1일봉 EMA 50 위에 가격
    if df_1d is not None and len(df_1d) > 0:
        if is_price_above_ema(df_1d, 50):
            mandatory_count += 1
            reasons.append("✅ [필수] 1일봉: 가격 > EMA50")
        else:
            reasons.append("❌ [필수] 1일봉: 가격 < EMA50")
    else:
        mandatory_count += 1  # 1일봉 없으면 통과
        reasons.append("⚠️ [필수] 1일봉 데이터 없음 (스킵)")

    # 2. EMA 정배열
    if is_ema_bullish_alignment(df_4h):
        mandatory_count += 1
        reasons.append("✅ [필수] 4시간봉 EMA 정배열 (13>21>50)")
    else:
        reasons.append("❌ [필수] EMA 정배열 아님")

    # 3. Higher Low 구조
    if is_higher_low(df_4h):
        mandatory_count += 1
        reasons.append("✅ [필수] Higher Low 구조 확인")
    else:
        reasons.append("❌ [필수] Higher Low 미확인")

    # 4. 거래량 > 14MA
    if is_volume_above_average(df_4h):
        mandatory_count += 1
        reasons.append("✅ [필수] 거래량 > 14MA 평균")
    else:
        reasons.append("❌ [필수] 거래량 부족")

    # === 추가 조건 ===

    # 1. RSI 상승 다이버전스
    if detect_rsi_bullish_divergence(df_4h):
        additional_count += 1
        reasons.append("✅ [추가] RSI 상승 다이버전스")

    # 2. RSI 30→40 반등
    if is_rsi_bounce_from_oversold(df_4h):
        additional_count += 1
        reasons.append("✅ [추가] RSI 과매도 반등 (30→40)")

    # 3. MACD 골든크로스 또는 히스토그램 양전환
    macd_cross = detect_macd_crossover(df_4h)
    if macd_cross == "golden":
        additional_count += 1
        reasons.append("✅ [추가] MACD 골든크로스")
    elif is_macd_histogram_positive(df_4h):
        additional_count += 1
        reasons.append("✅ [추가] MACD 히스토그램 양전환")

    # 4. OBV 상승 추세
    if is_obv_trending_up(df_4h):
        additional_count += 1
        reasons.append("✅ [추가] OBV 상승 추세")

    # === 신호 판정 ===
    # 필수 4개 + 추가 2개 이상
    if mandatory_count >= 4 and additional_count >= 2:
        # 손절가 계산: 최근 스윙 로우 - 0.5% 버퍼
        swing_lows = find_swing_lows(df_4h.tail(60), lookback=3)
        current_price = df_4h["close"].iloc[-1]

        if swing_lows:
            stop_loss = swing_lows[-1] * 0.995  # 0.5% 버퍼
        else:
            stop_loss = current_price * 0.97  # 3% 기본 손절

        # 최대 손절 3% 제한
        max_sl = current_price * 0.97
        stop_loss = max(stop_loss, max_sl)

        risk = current_price - stop_loss
        tp1 = current_price + (risk * 1.5)  # R:R 1.5:1

        confidence = min(1.0, (mandatory_count / 4 * 0.6) + (additional_count / 4 * 0.4))

        signal = Signal(
            signal_type=SignalType.LONG,
            confidence=confidence,
            stop_loss=stop_loss,
            take_profit_1=tp1,
            entry_price=current_price,
            reasons=reasons,
            mandatory_met=mandatory_count,
            additional_met=additional_count,
        )
        logger.info(f"🟢 롱 신호 생성 | 신뢰도: {confidence:.0%} | 필수: {mandatory_count}/4, 추가: {additional_count}")
    else:
        signal.reasons = reasons
        signal.mandatory_met = mandatory_count
        signal.additional_met = additional_count

    return signal


def check_short_entry(
    df_4h: pd.DataFrame,
    df_1d: Optional[pd.DataFrame] = None,
) -> Signal:
    """
    숏 포지션 진입 조건 검사

    필수 조건 (4개 모두):
    1. 1일봉 EMA 50 아래에 가격
    2. 4시간봉 EMA 역배열 (13 < 21 < 50)
    3. Lower High 구조
    4. 진입 캔들 거래량 > 14MA

    추가 조건 (2개 이상):
    1. RSI 하락 다이버전스
    2. RSI 70→60 하락
    3. MACD 데드크로스 또는 히스토그램 음전환
    4. OBV 하락 추세
    """
    signal = Signal(signal_type=SignalType.NO_SIGNAL)
    mandatory_count = 0
    additional_count = 0
    reasons = []

    # === 필수 조건 ===
    if df_1d is not None and len(df_1d) > 0:
        if is_price_below_ema(df_1d, 50):
            mandatory_count += 1
            reasons.append("✅ [필수] 1일봉: 가격 < EMA50")
        else:
            reasons.append("❌ [필수] 1일봉: 가격 > EMA50")
    else:
        mandatory_count += 1
        reasons.append("⚠️ [필수] 1일봉 데이터 없음 (스킵)")

    if is_ema_bearish_alignment(df_4h):
        mandatory_count += 1
        reasons.append("✅ [필수] 4시간봉 EMA 역배열 (13<21<50)")
    else:
        reasons.append("❌ [필수] EMA 역배열 아님")

    if is_lower_high(df_4h):
        mandatory_count += 1
        reasons.append("✅ [필수] Lower High 구조 확인")
    else:
        reasons.append("❌ [필수] Lower High 미확인")

    if is_volume_above_average(df_4h):
        mandatory_count += 1
        reasons.append("✅ [필수] 거래량 > 14MA 평균")
    else:
        reasons.append("❌ [필수] 거래량 부족")

    # === 추가 조건 ===
    if detect_rsi_bearish_divergence(df_4h):
        additional_count += 1
        reasons.append("✅ [추가] RSI 하락 다이버전스")

    if is_rsi_drop_from_overbought(df_4h):
        additional_count += 1
        reasons.append("✅ [추가] RSI 과매수 하락 (70→60)")

    macd_cross = detect_macd_crossover(df_4h)
    if macd_cross == "death":
        additional_count += 1
        reasons.append("✅ [추가] MACD 데드크로스")
    elif is_macd_histogram_negative(df_4h):
        additional_count += 1
        reasons.append("✅ [추가] MACD 히스토그램 음전환")

    if is_obv_trending_down(df_4h):
        additional_count += 1
        reasons.append("✅ [추가] OBV 하락 추세")

    # === 신호 판정 ===
    if mandatory_count >= 4 and additional_count >= 2:
        swing_highs = find_swing_highs(df_4h.tail(60), lookback=3)
        current_price = df_4h["close"].iloc[-1]

        if swing_highs:
            stop_loss = swing_highs[-1] * 1.005
        else:
            stop_loss = current_price * 1.03

        max_sl = current_price * 1.03
        stop_loss = min(stop_loss, max_sl)

        risk = stop_loss - current_price
        tp1 = current_price - (risk * 1.5)

        confidence = min(1.0, (mandatory_count / 4 * 0.6) + (additional_count / 4 * 0.4))

        signal = Signal(
            signal_type=SignalType.SHORT,
            confidence=confidence,
            stop_loss=stop_loss,
            take_profit_1=tp1,
            entry_price=current_price,
            reasons=reasons,
            mandatory_met=mandatory_count,
            additional_met=additional_count,
        )
        logger.info(f"🔴 숏 신호 생성 | 신뢰도: {confidence:.0%} | 필수: {mandatory_count}/4, 추가: {additional_count}")
    else:
        signal.reasons = reasons
        signal.mandatory_met = mandatory_count
        signal.additional_met = additional_count

    return signal


def check_close_signal(
    df_4h: pd.DataFrame,
    position_side: str,
) -> Signal:
    """
    청산 신호 검사

    청산 조건:
    - 반대 방향 EMA 크로스오버
    - RSI 반대 다이버전스
    - MACD 반대 크로스오버
    """
    signal = Signal(signal_type=SignalType.NO_SIGNAL)
    reasons = []

    ema_cross = detect_ema_crossover(df_4h, fast=13, slow=21)
    macd_cross = detect_macd_crossover(df_4h)

    if position_side == "long":
        if ema_cross == "death":
            reasons.append("⚠️ EMA 데드크로스 → 롱 청산")
        if detect_rsi_bearish_divergence(df_4h):
            reasons.append("⚠️ RSI 하락 다이버전스 → 롱 청산")
        if macd_cross == "death":
            reasons.append("⚠️ MACD 데드크로스 → 롱 청산")

        if len(reasons) >= 2:
            signal = Signal(
                signal_type=SignalType.CLOSE_LONG,
                confidence=min(1.0, len(reasons) * 0.35),
                reasons=reasons,
            )
            logger.warning(f"🟡 롱 청산 신호 | 이유: {len(reasons)}개")

    elif position_side == "short":
        if ema_cross == "golden":
            reasons.append("⚠️ EMA 골든크로스 → 숏 청산")
        if detect_rsi_bullish_divergence(df_4h):
            reasons.append("⚠️ RSI 상승 다이버전스 → 숏 청산")
        if macd_cross == "golden":
            reasons.append("⚠️ MACD 골든크로스 → 숏 청산")

        if len(reasons) >= 2:
            signal = Signal(
                signal_type=SignalType.CLOSE_SHORT,
                confidence=min(1.0, len(reasons) * 0.35),
                reasons=reasons,
            )
            logger.warning(f"🟡 숏 청산 신호 | 이유: {len(reasons)}개")

    signal.reasons = reasons
    return signal
