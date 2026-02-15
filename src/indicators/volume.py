"""
거래량 지표 (Volume Indicators)
OBV, 거래량 MA, 거래량 분석
"""
import pandas as pd
import numpy as np
from typing import Optional

from src.config.constants import VOLUME_MA_PERIOD
from src.utils.logger import setup_logger

logger = setup_logger("indicators.volume")


def calculate_obv(df: pd.DataFrame) -> pd.Series:
    """
    OBV (On-Balance Volume) 계산

    가격 상승 시 거래량 추가, 하락 시 차감
    """
    obv = pd.Series(0.0, index=df.index, dtype=float)

    for i in range(1, len(df)):
        if df["close"].iloc[i] > df["close"].iloc[i - 1]:
            obv.iloc[i] = obv.iloc[i - 1] + df["volume"].iloc[i]
        elif df["close"].iloc[i] < df["close"].iloc[i - 1]:
            obv.iloc[i] = obv.iloc[i - 1] - df["volume"].iloc[i]
        else:
            obv.iloc[i] = obv.iloc[i - 1]

    return obv


def calculate_volume_ma(df: pd.DataFrame, period: int = VOLUME_MA_PERIOD) -> pd.Series:
    """거래량 이동평균"""
    return df["volume"].rolling(window=period).mean()


def add_volume_indicators(df: pd.DataFrame, period: int = VOLUME_MA_PERIOD) -> pd.DataFrame:
    """DataFrame에 거래량 지표 추가"""
    df["obv"] = calculate_obv(df)
    df["volume_ma"] = calculate_volume_ma(df, period)
    df["volume_ratio"] = df["volume"] / df["volume_ma"]
    return df


def is_volume_above_average(df: pd.DataFrame, row_idx: int = -1) -> bool:
    """현재 거래량이 14MA 평균 이상인지 확인"""
    if "volume_ma" not in df.columns:
        return False
    row = df.iloc[row_idx]
    vol_ma = row.get("volume_ma", 0)
    if pd.isna(vol_ma) or vol_ma == 0:
        return False
    return row["volume"] > vol_ma


def is_volume_too_low(df: pd.DataFrame, threshold: float = 0.5, row_idx: int = -1) -> bool:
    """
    거래량이 너무 낮은지 확인 (진입 회피 조건)
    최근 4시간 평균 거래량 < 14MA의 50%
    """
    if "volume_ma" not in df.columns:
        return False
    row = df.iloc[row_idx]
    vol_ma = row.get("volume_ma", 0)
    if pd.isna(vol_ma) or vol_ma == 0:
        return True
    return row["volume"] < vol_ma * threshold


def is_obv_trending_up(df: pd.DataFrame, lookback: int = 10) -> bool:
    """OBV 상승 추세 확인"""
    if "obv" not in df.columns or len(df) < lookback:
        return False
    recent_obv = df["obv"].tail(lookback)
    # 선형 회귀 기울기로 추세 판단
    x = np.arange(len(recent_obv))
    slope = np.polyfit(x, recent_obv.values, 1)[0]
    return slope > 0


def is_obv_trending_down(df: pd.DataFrame, lookback: int = 10) -> bool:
    """OBV 하락 추세 확인"""
    if "obv" not in df.columns or len(df) < lookback:
        return False
    recent_obv = df["obv"].tail(lookback)
    x = np.arange(len(recent_obv))
    slope = np.polyfit(x, recent_obv.values, 1)[0]
    return slope < 0
