"""
매매 신호 생성 (Signal Generator)
TRADING_STRATEGY.md의 진입/청산 조건 구현

v2.1 — 15분봉 셋업 + 5분봉 타이밍 (하이브리드 전략)
- 15분봉 (Setup): 직전 마감 캔들 기준 (iloc[-2]) -> 리페인팅 방지
- 5분봉 (Trigger): 직전 마감 캔들 기준 (iloc[-2]) -> 정밀 타이밍
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
from src.config.constants import MIN_RR_RATIO, MAX_STOP_LOSS_PERCENT, STOP_LOSS_BUFFER_PERCENT, MACD_HISTOGRAM_MODE, ENTRY_VOLUME_THRESHOLD
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
    df_15m: pd.DataFrame,
    df_1h: Optional[pd.DataFrame] = None,
    df_5m: Optional[pd.DataFrame] = None,
) -> Signal:
    """
    롱 포지션 진입 조건 검사 (v2.1 — 하이브리드 전략)
    """
    signal = Signal(signal_type=SignalType.NO_SIGNAL)
    mandatory_count = 0
    additional_count = 0
    reasons = []

    # 기준 인덱스: 마감된 캔들 사용 (-2)
    IDX = -2

    if len(df_15m) < 2:
        return Signal(signal_type=SignalType.NO_SIGNAL, reasons=["데이터 부족 (15m)"])

    # === 필수 조건 ===

    # 1. [추세] 1시간봉 EMA 50 위에 가격 + EMA 9 > EMA 50
    if df_1h is not None and len(df_1h) > 0:
        current_price = df_15m["close"].iloc[IDX] # 15분봉 마감 가격 기준
        
        ema50_1h = df_1h["ema_50"].iloc[-1] if "ema_50" in df_1h.columns else 0
        ema9_1h = df_1h["ema_9"].iloc[-1] if "ema_9" in df_1h.columns else 0
        
        price_above = current_price > ema50_1h
        ema_9_above_50 = ema9_1h > ema50_1h

        if price_above and ema_9_above_50:
            mandatory_count += 1
            reasons.append("✅ [필수] 1시간봉: 가격 > EMA50 & EMA9 > EMA50")
        elif price_above:
            mandatory_count += 1
            reasons.append("✅ [필수] 1시간봉: 가격 > EMA50 (EMA9 미확인)")
        else:
            reasons.append("❌ [필수] 1시간봉: 가격 < EMA50")
    else:
        mandatory_count += 1
        reasons.append("⚠️ [필수] 1시간봉 데이터 없음 (스킵)")

    # 2. [모멘텀] 15분봉(마감) RSI > 40 + MACD 히스토그램 상승 전환
    rsi_ok = False
    macd_ok = False

    if "rsi" in df_15m.columns:
        closed_rsi = df_15m["rsi"].iloc[IDX]
        rsi_ok = closed_rsi > 40

    if "macd_hist" in df_15m.columns:
        hist_now = df_15m["macd_hist"].iloc[IDX]      # 마감된 캔들
        hist_prev = df_15m["macd_hist"].iloc[IDX-1]   # 그 전 캔들
        
        if MACD_HISTOGRAM_MODE == "strict":
            macd_ok = hist_now > 0
        else:
            macd_ok = hist_now > hist_prev

    if rsi_ok and macd_ok:
        mandatory_count += 1
        rsi_val = df_15m["rsi"].iloc[IDX]
        mode_label = "양전환" if MACD_HISTOGRAM_MODE == "strict" else "상승"
        reasons.append(f"✅ [필수] 15분봉(마감): RSI {rsi_val:.0f} > 40 + MACD {mode_label}")
    else:
        reasons.append(f"❌ [필수] 15분봉(마감) 모멘텀 부족 (RSI>40: {rsi_ok}, MACD↑: {macd_ok})")

    # 3. [거래량] 15분봉(마감) 거래량 > 14MA의 70%
    if is_volume_above_average(df_15m, row_idx=IDX, threshold=ENTRY_VOLUME_THRESHOLD):
        mandatory_count += 1
        reasons.append(f"✅ [필수] 15분봉(마감) 거래량 > 14MA의 {ENTRY_VOLUME_THRESHOLD:.0%}")
    else:
        reasons.append(f"❌ [필수] 15분봉(마감) 거래량 부족 (< {ENTRY_VOLUME_THRESHOLD:.0%})")

    # === 추가 조건 ===

    # 1. [EMA] 5분봉(마감) EMA 9 > EMA 21 (단기 정배열)
    if df_5m is not None and len(df_5m) > 2:
        if "ema_9" in df_5m.columns and "ema_21" in df_5m.columns:
            if df_5m["ema_9"].iloc[IDX] > df_5m["ema_21"].iloc[IDX]:
                additional_count += 1
                reasons.append("✅ [추가] 5분봉(마감) EMA 9 > EMA 21 (단기 정배열)")

    # 2. [RSI] 15분봉(마감) RSI 상승 다이버전스
    # 마감 캔들까지만 잘라서 전달
    if detect_rsi_bullish_divergence(df_15m.iloc[:IDX+1]): 
        additional_count += 1
        reasons.append("✅ [추가] 15분봉(마감) RSI 상승 다이버전스")

    # 3. [구조] 15분봉(마감) Higher Low
    if is_higher_low(df_15m.iloc[:IDX+1]):
        additional_count += 1
        reasons.append("✅ [추가] 15분봉(마감) Higher Low 구조 확인")

    # 4. [OBV] 15분봉(마감) OBV 상승 추세
    if is_obv_trending_up(df_15m.iloc[:IDX+1]):
        additional_count += 1
        reasons.append("✅ [추가] 15분봉(마감) OBV 상승 추세")

    # === 신호 판정 ===
    if mandatory_count >= 3 and additional_count >= 1:
        swing_lows = find_swing_lows(df_15m.iloc[:IDX+1].tail(60), lookback=3)
        current_price = df_15m["close"].iloc[IDX]

        buffer = 1 - (STOP_LOSS_BUFFER_PERCENT / 100)
        max_sl_pct = 1 - (MAX_STOP_LOSS_PERCENT / 100)

        if swing_lows:
            stop_loss = swing_lows[-1] * buffer
        else:
            stop_loss = current_price * max_sl_pct

        max_sl = current_price * max_sl_pct
        stop_loss = max(stop_loss, max_sl)

        risk = current_price - stop_loss
        tp1 = current_price + (risk * 1.5)

        confidence = min(1.0, (mandatory_count / 3 * 0.6) + (additional_count / 4 * 0.4))

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
        logger.info(f"🟢 롱 신호 생성 (마감봉 기준) | 신뢰도: {confidence:.0%} | 필수: {mandatory_count}/3, 추가: {additional_count}")
    else:
        signal.reasons = reasons
        signal.mandatory_met = mandatory_count
        signal.additional_met = additional_count

    return signal


def check_short_entry(
    df_15m: pd.DataFrame,
    df_1h: Optional[pd.DataFrame] = None,
    df_5m: Optional[pd.DataFrame] = None,
) -> Signal:
    """
    숏 포지션 진입 조건 검사 (v2.1 — 하이브리드 전략)
    """
    signal = Signal(signal_type=SignalType.NO_SIGNAL)
    mandatory_count = 0
    additional_count = 0
    reasons = []

    IDX = -2

    if len(df_15m) < 2:
        return Signal(signal_type=SignalType.NO_SIGNAL, reasons=["데이터 부족 (15m)"])

    # === 필수 조건 ===

    # 1. [추세] 1시간봉 EMA 50 아래에 가격 + EMA 9 < EMA 50
    if df_1h is not None and len(df_1h) > 0:
        current_price = df_15m["close"].iloc[IDX]
        
        ema50_1h = df_1h["ema_50"].iloc[-1] if "ema_50" in df_1h.columns else 0
        ema9_1h = df_1h["ema_9"].iloc[-1] if "ema_9" in df_1h.columns else 0
        
        price_below = current_price < ema50_1h
        ema_9_below_50 = ema9_1h < ema50_1h

        if price_below and ema_9_below_50:
            mandatory_count += 1
            reasons.append("✅ [필수] 1시간봉: 가격 < EMA50 & EMA9 < EMA50")
        elif price_below:
            mandatory_count += 1
            reasons.append("✅ [필수] 1시간봉: 가격 < EMA50 (EMA9 미확인)")
        else:
            reasons.append("❌ [필수] 1시간봉: 가격 > EMA50")
    else:
        mandatory_count += 1
        reasons.append("⚠️ [필수] 1시간봉 데이터 없음 (스킵)")

    # 2. [모멘텀] 15분봉(마감) RSI < 60 + MACD 히스토그램 하락 전환
    rsi_ok = False
    macd_ok = False

    if "rsi" in df_15m.columns:
        closed_rsi = df_15m["rsi"].iloc[IDX]
        rsi_ok = closed_rsi < 60

    if "macd_hist" in df_15m.columns:
        hist_now = df_15m["macd_hist"].iloc[IDX]
        hist_prev = df_15m["macd_hist"].iloc[IDX-1]
        
        if MACD_HISTOGRAM_MODE == "strict":
            macd_ok = hist_now < 0
        else:
            macd_ok = hist_now < hist_prev

    if rsi_ok and macd_ok:
        mandatory_count += 1
        rsi_val = df_15m["rsi"].iloc[IDX]
        mode_label = "음전환" if MACD_HISTOGRAM_MODE == "strict" else "하락"
        reasons.append(f"✅ [필수] 15분봉(마감): RSI {rsi_val:.0f} < 60 + MACD {mode_label}")
    else:
        reasons.append(f"❌ [필수] 15분봉(마감) 모멘텀 부족 (RSI<60: {rsi_ok}, MACD↓: {macd_ok})")

    # 3. [거래량] 15분봉(마감) 거래량 > 14MA의 70%
    if is_volume_above_average(df_15m, row_idx=IDX, threshold=ENTRY_VOLUME_THRESHOLD):
        mandatory_count += 1
        reasons.append(f"✅ [필수] 15분봉(마감) 거래량 > 14MA의 {ENTRY_VOLUME_THRESHOLD:.0%}")
    else:
        reasons.append(f"❌ [필수] 15분봉(마감) 거래량 부족 (< {ENTRY_VOLUME_THRESHOLD:.0%})")

    # === 추가 조건 ===

    # 1. [EMA] 5분봉(마감) EMA 9 < EMA 21 (단기 역배열)
    if df_5m is not None and len(df_5m) > 2:
        if "ema_9" in df_5m.columns and "ema_21" in df_5m.columns:
            if df_5m["ema_9"].iloc[IDX] < df_5m["ema_21"].iloc[IDX]:
                additional_count += 1
                reasons.append("✅ [추가] 5분봉(마감) EMA 9 < EMA 21 (단기 역배열)")

    # 2. [RSI] 15분봉(마감) RSI 하락 다이버전스
    if detect_rsi_bearish_divergence(df_15m.iloc[:IDX+1]):
        additional_count += 1
        reasons.append("✅ [추가] 15분봉(마감) RSI 하락 다이버전스")

    # 3. [구조] 15분봉(마감) Lower High
    if is_lower_high(df_15m.iloc[:IDX+1]):
        additional_count += 1
        reasons.append("✅ [추가] 15분봉(마감) Lower High 구조 확인")

    # 4. [OBV] 15분봉(마감) OBV 하락 추세
    if is_obv_trending_down(df_15m.iloc[:IDX+1]):
        additional_count += 1
        reasons.append("✅ [추가] 15분봉(마감) OBV 하락 추세")

    # === 신호 판정 ===
    if mandatory_count >= 3 and additional_count >= 1:
        swing_highs = find_swing_highs(df_15m.iloc[:IDX+1].tail(60), lookback=3)
        current_price = df_15m["close"].iloc[IDX]

        buffer = 1 + (STOP_LOSS_BUFFER_PERCENT / 100)
        max_sl_pct = 1 + (MAX_STOP_LOSS_PERCENT / 100)

        if swing_highs:
            stop_loss = swing_highs[-1] * buffer
        else:
            stop_loss = current_price * max_sl_pct

        max_sl = current_price * max_sl_pct
        stop_loss = min(stop_loss, max_sl)

        risk = stop_loss - current_price
        tp1 = current_price - (risk * 1.5)

        confidence = min(1.0, (mandatory_count / 3 * 0.6) + (additional_count / 4 * 0.4))

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
        logger.info(f"🔴 숏 신호 생성 (마감봉 기준) | 신뢰도: {confidence:.0%} | 필수: {mandatory_count}/3, 추가: {additional_count}")
    else:
        signal.reasons = reasons
        signal.mandatory_met = mandatory_count
        signal.additional_met = additional_count

    return signal


def check_close_signal(
    df_15m: pd.DataFrame,
    position_side: str,
) -> Signal:
    """
    청산 신호 검사 (15분봉 마감 기준)
    """
    signal = Signal(signal_type=SignalType.NO_SIGNAL)
    reasons = []

    IDX = -2
    df_closed = df_15m.iloc[:IDX+1]

    ema_cross = detect_ema_crossover(df_closed, fast=9, slow=21)
    macd_cross = detect_macd_crossover(df_closed)

    if position_side == "long":
        if ema_cross == "death":
            reasons.append("⚠️ EMA 데드크로스 (9/21) → 롱 청산")
        if detect_rsi_bearish_divergence(df_closed):
            reasons.append("⚠️ RSI 하락 다이버전스 → 롱 청산")
        if macd_cross == "death":
            reasons.append("⚠️ MACD 데드크로스 → 롱 청산")

        if len(reasons) >= 2:
            signal = Signal(
                signal_type=SignalType.CLOSE_LONG,
                confidence=min(1.0, len(reasons) * 0.35),
                reasons=reasons,
            )
            logger.warning(f"🟡 롱 청산 신호 (마감봉) | 이유: {len(reasons)}개")

    elif position_side == "short":
        if ema_cross == "golden":
            reasons.append("⚠️ EMA 골든크로스 (9/21) → 숏 청산")
        if detect_rsi_bullish_divergence(df_closed):
            reasons.append("⚠️ RSI 상승 다이버전스 → 숏 청산")
        if macd_cross == "golden":
            reasons.append("⚠️ MACD 골든크로스 → 숏 청산")

        if len(reasons) >= 2:
            signal = Signal(
                signal_type=SignalType.CLOSE_SHORT,
                confidence=min(1.0, len(reasons) * 0.35),
                reasons=reasons,
            )
            logger.warning(f"🟡 숏 청산 신호 (마감봉) | 이유: {len(reasons)}개")

    signal.reasons = reasons
    return signal
