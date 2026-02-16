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


def is_volume_above_average(df: pd.DataFrame, row_idx: int = -1, threshold: float = 1.0) -> bool:
    """
    현재 거래량이 14MA의 일정 비율 이상인지 확인

    Args:
        df: 데이터프레임
        row_idx: 확인할 행 인덱스
        threshold: 기준 비율 (1.0 = 평균, 0.7 = 평균의 70%)
    """
    if "volume_ma" not in df.columns:
        return False
    row = df.iloc[row_idx]
    vol_ma = row.get("volume_ma", 0)
    if pd.isna(vol_ma) or vol_ma == 0:
        return False
    return row["volume"] > (vol_ma * threshold)


def is_volume_too_low(df: pd.DataFrame, threshold: float = 0.5, row_idx: int = -1) -> bool:
    """
    거래량이 너무 낮은지 확인 (진입 회피 조건)
    해당 캔들의 거래량 < 14MA의 threshold%

    Args:
        df: 지표가 추가된 DataFrame
        threshold: 기준 비율 (기본 0.5 = 50%)
        row_idx: 확인할 행 인덱스 (기본 -1, 직전 마감 캔들은 -2)
    """
    if "volume_ma" not in df.columns:
        logger.debug("volume_ma 컬럼 없음")
        return False

    row = df.iloc[row_idx]
    volume = row.get("volume", 0)
    vol_ma = row.get("volume_ma", 0)

    if pd.isna(vol_ma) or vol_ma == 0:
        logger.debug(f"volume_ma 값 없음 또는 0: {vol_ma}")
        return True

    volume_ratio = volume / vol_ma
    is_low = volume < vol_ma * threshold

    # 디버깅 로그 (INFO 레벨로 출력하여 Railway에서 확인 가능)
    logger.info(
        f"[볼륨체크] idx={row_idx} | 거래량={volume:,.0f} | "
        f"14MA={vol_ma:,.0f} | 비율={volume_ratio:.2%} | "
        f"기준={threshold:.0%} | 회피={is_low}"
    )

    return is_low


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
