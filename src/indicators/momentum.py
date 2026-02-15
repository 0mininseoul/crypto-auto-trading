"""
모멘텀 지표 (Momentum Indicators)
RSI, MACD, 다이버전스 감지
"""
import pandas as pd
import numpy as np
from typing import Optional, Tuple

from src.config.constants import RSI_PERIOD, MACD_FAST, MACD_SLOW, MACD_SIGNAL
from src.utils.logger import setup_logger

logger = setup_logger("indicators.momentum")


def calculate_rsi(df: pd.DataFrame, period: int = RSI_PERIOD, column: str = "close") -> pd.Series:
    """
    RSI (상대강도지수) 계산

    Args:
        df: OHLCV DataFrame
        period: RSI 기간 (기본: 14)

    Returns:
        RSI Series (0-100)
    """
    delta = df[column].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_macd(
    df: pd.DataFrame,
    fast: int = MACD_FAST,
    slow: int = MACD_SLOW,
    signal: int = MACD_SIGNAL,
    column: str = "close",
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    MACD 계산

    Returns:
        (macd_line, signal_line, histogram)
    """
    ema_fast = df[column].ewm(span=fast, adjust=False).mean()
    ema_slow = df[column].ewm(span=slow, adjust=False).mean()

    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


def add_rsi(df: pd.DataFrame, period: int = RSI_PERIOD) -> pd.DataFrame:
    """DataFrame에 RSI 컬럼 추가"""
    df["rsi"] = calculate_rsi(df, period)
    return df


def add_macd(
    df: pd.DataFrame,
    fast: int = MACD_FAST,
    slow: int = MACD_SLOW,
    signal: int = MACD_SIGNAL,
) -> pd.DataFrame:
    """DataFrame에 MACD 컬럼 추가"""
    macd_line, signal_line, histogram = calculate_macd(df, fast, slow, signal)
    df["macd"] = macd_line
    df["macd_signal"] = signal_line
    df["macd_hist"] = histogram
    return df


def is_rsi_oversold(df: pd.DataFrame, threshold: float = 30, row_idx: int = -1) -> bool:
    """RSI 과매도 상태 확인"""
    if "rsi" not in df.columns:
        return False
    return df["rsi"].iloc[row_idx] < threshold


def is_rsi_overbought(df: pd.DataFrame, threshold: float = 70, row_idx: int = -1) -> bool:
    """RSI 과매수 상태 확인"""
    if "rsi" not in df.columns:
        return False
    return df["rsi"].iloc[row_idx] > threshold


def detect_rsi_bullish_divergence(df: pd.DataFrame, lookback: int = 20) -> bool:
    """
    RSI 상승 다이버전스 감지
    가격은 저점 하락, RSI는 저점 상승 → 롱 신호
    """
    if "rsi" not in df.columns or len(df) < lookback:
        return False

    recent = df.tail(lookback)
    mid = lookback // 2

    # 가격 저점 비교
    price_low_1 = recent["low"].iloc[:mid].min()
    price_low_2 = recent["low"].iloc[mid:].min()

    # RSI 저점 비교
    rsi_low_1 = recent["rsi"].iloc[:mid].min()
    rsi_low_2 = recent["rsi"].iloc[mid:].min()

    # 가격 저점↓ + RSI 저점↑ = 상승 다이버전스
    return price_low_2 < price_low_1 and rsi_low_2 > rsi_low_1


def detect_rsi_bearish_divergence(df: pd.DataFrame, lookback: int = 20) -> bool:
    """
    RSI 하락 다이버전스 감지
    가격은 고점 상승, RSI는 고점 하락 → 숏 신호
    """
    if "rsi" not in df.columns or len(df) < lookback:
        return False

    recent = df.tail(lookback)
    mid = lookback // 2

    price_high_1 = recent["high"].iloc[:mid].max()
    price_high_2 = recent["high"].iloc[mid:].max()

    rsi_high_1 = recent["rsi"].iloc[:mid].max()
    rsi_high_2 = recent["rsi"].iloc[mid:].max()

    # 가격 고점↑ + RSI 고점↓ = 하락 다이버전스
    return price_high_2 > price_high_1 and rsi_high_2 < rsi_high_1


def is_rsi_bounce_from_oversold(df: pd.DataFrame, lookback: int = 10) -> bool:
    """RSI 30 이하에서 반등 후 40 돌파 확인"""
    if "rsi" not in df.columns or len(df) < lookback:
        return False

    recent = df["rsi"].tail(lookback)
    was_oversold = recent.min() <= 30
    currently_above_40 = recent.iloc[-1] > 40

    return was_oversold and currently_above_40


def is_rsi_drop_from_overbought(df: pd.DataFrame, lookback: int = 10) -> bool:
    """RSI 70 이상에서 하락 후 60 하향 돌파 확인"""
    if "rsi" not in df.columns or len(df) < lookback:
        return False

    recent = df["rsi"].tail(lookback)
    was_overbought = recent.max() >= 70
    currently_below_60 = recent.iloc[-1] < 60

    return was_overbought and currently_below_60


def detect_macd_crossover(df: pd.DataFrame) -> Optional[str]:
    """
    MACD 크로스오버 감지

    Returns:
        'golden' (골든크로스), 'death' (데드크로스), 또는 None
    """
    if "macd" not in df.columns or "macd_signal" not in df.columns:
        return None
    if len(df) < 2:
        return None

    curr_macd = df["macd"].iloc[-1]
    curr_signal = df["macd_signal"].iloc[-1]
    prev_macd = df["macd"].iloc[-2]
    prev_signal = df["macd_signal"].iloc[-2]

    if prev_macd <= prev_signal and curr_macd > curr_signal:
        return "golden"
    if prev_macd >= prev_signal and curr_macd < curr_signal:
        return "death"

    return None


def is_macd_histogram_positive(df: pd.DataFrame, row_idx: int = -1) -> bool:
    """MACD 히스토그램 양전환 확인"""
    if "macd_hist" not in df.columns:
        return False
    if len(df) < 2:
        return False
    curr = df["macd_hist"].iloc[row_idx]
    prev = df["macd_hist"].iloc[row_idx - 1]
    return prev < 0 and curr > 0


def is_macd_histogram_negative(df: pd.DataFrame, row_idx: int = -1) -> bool:
    """MACD 히스토그램 음전환 확인"""
    if "macd_hist" not in df.columns:
        return False
    if len(df) < 2:
        return False
    curr = df["macd_hist"].iloc[row_idx]
    prev = df["macd_hist"].iloc[row_idx - 1]
    return prev > 0 and curr < 0
