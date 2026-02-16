"""
추세 지표 (Trend Indicators)
EMA, SMA, 추세 방향 판별
"""
import pandas as pd
import numpy as np
from typing import List, Optional, Tuple

from src.config.constants import EMA_PERIODS
from src.utils.logger import setup_logger

logger = setup_logger("indicators.trend")


def calculate_ema(df: pd.DataFrame, period: int, column: str = "close") -> pd.Series:
    """
    지수이동평균 (EMA) 계산

    Args:
        df: OHLCV DataFrame
        period: EMA 기간
        column: 계산 대상 컬럼

    Returns:
        EMA Series
    """
    return df[column].ewm(span=period, adjust=False).mean()


def calculate_sma(df: pd.DataFrame, period: int, column: str = "close") -> pd.Series:
    """단순이동평균 (SMA) 계산"""
    return df[column].rolling(window=period).mean()


def add_all_emas(df: pd.DataFrame, periods: List[int] = None) -> pd.DataFrame:
    """
    모든 EMA 컬럼 추가

    Args:
        df: OHLCV DataFrame
        periods: EMA 기간 목록 (기본: [9, 21, 50, 200])

    Returns:
        EMA 컬럼이 추가된 DataFrame
    """
    if periods is None:
        periods = EMA_PERIODS

    for p in periods:
        df[f"ema_{p}"] = calculate_ema(df, p)

    return df


def is_ema_bullish_alignment(df: pd.DataFrame, row_idx: int = -1) -> bool:
    """
    EMA 정배열 확인 (롱 조건)
    EMA 9 > EMA 21 > EMA 50

    Args:
        df: EMA 컬럼이 포함된 DataFrame
        row_idx: 확인할 행 인덱스 (기본: 마지막)
    """
    row = df.iloc[row_idx]
    try:
        return (
            row["ema_9"] > row["ema_21"] > row["ema_50"]
        )
    except KeyError:
        logger.warning("EMA 컬럼이 없습니다. add_all_emas()를 먼저 호출하세요.")
        return False


def is_ema_bearish_alignment(df: pd.DataFrame, row_idx: int = -1) -> bool:
    """
    EMA 역배열 확인 (숏 조건)
    EMA 9 < EMA 21 < EMA 50
    """
    row = df.iloc[row_idx]
    try:
        return (
            row["ema_9"] < row["ema_21"] < row["ema_50"]
        )
    except KeyError:
        logger.warning("EMA 컬럼이 없습니다. add_all_emas()를 먼저 호출하세요.")
        return False


def is_price_above_ema(df: pd.DataFrame, period: int, row_idx: int = -1) -> bool:
    """현재 가격이 특정 EMA 위에 있는지 확인"""
    row = df.iloc[row_idx]
    return row["close"] > row.get(f"ema_{period}", float("inf"))


def is_price_below_ema(df: pd.DataFrame, period: int, row_idx: int = -1) -> bool:
    """현재 가격이 특정 EMA 아래에 있는지 확인"""
    row = df.iloc[row_idx]
    return row["close"] < row.get(f"ema_{period}", 0)


def detect_ema_crossover(df: pd.DataFrame, fast: int = 13, slow: int = 21) -> Optional[str]:
    """
    EMA 크로스오버 감지

    Returns:
        'golden' (골든크로스), 'death' (데드크로스), 또는 None
    """
    if len(df) < 2:
        return None

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    fast_col = f"ema_{fast}"
    slow_col = f"ema_{slow}"

    if fast_col not in df.columns or slow_col not in df.columns:
        return None

    # 골든크로스: 이전에 fast < slow → 현재 fast > slow
    if prev[fast_col] <= prev[slow_col] and curr[fast_col] > curr[slow_col]:
        return "golden"

    # 데드크로스: 이전에 fast > slow → 현재 fast < slow
    if prev[fast_col] >= prev[slow_col] and curr[fast_col] < curr[slow_col]:
        return "death"

    return None


def find_swing_highs(df: pd.DataFrame, lookback: int = 5) -> List[float]:
    """스윙 하이 지점 찾기"""
    highs = []
    for i in range(lookback, len(df) - lookback):
        if df["high"].iloc[i] == df["high"].iloc[i - lookback:i + lookback + 1].max():
            highs.append(df["high"].iloc[i])
    return highs


def find_swing_lows(df: pd.DataFrame, lookback: int = 5) -> List[float]:
    """스윙 로우 지점 찾기"""
    lows = []
    for i in range(lookback, len(df) - lookback):
        if df["low"].iloc[i] == df["low"].iloc[i - lookback:i + lookback + 1].min():
            lows.append(df["low"].iloc[i])
    return lows


def is_higher_low(df: pd.DataFrame, lookback: int = 20) -> bool:
    """Higher Low 구조 확인 (상승 구조)"""
    lows = find_swing_lows(df.tail(lookback * 3), lookback=3)
    if len(lows) >= 2:
        return lows[-1] > lows[-2]
    return False


def is_lower_high(df: pd.DataFrame, lookback: int = 20) -> bool:
    """Lower High 구조 확인 (하락 구조)"""
    highs = find_swing_highs(df.tail(lookback * 3), lookback=3)
    if len(highs) >= 2:
        return highs[-1] < highs[-2]
    return False
