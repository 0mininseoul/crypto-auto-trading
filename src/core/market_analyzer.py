"""
시장 분석 엔진 (Market Analyzer)
지표 계산 + 시장 상태 평가 + 진입 회피 조건 + 신호 생성
"""
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional

import pandas as pd
import numpy as np

from src.exchange.data_fetcher import DataFetcher
from src.indicators.signals import (
    prepare_dataframe,
    check_long_entry,
    check_short_entry,
    check_close_signal,
    Signal,
    SignalType,
)
from src.indicators.volume import is_volume_too_low
from src.config.constants import (
    EXTREME_VOLATILITY_MULTIPLIER,
    LOW_VOLUME_THRESHOLD,
    MIN_RR_RATIO,
)
from src.utils.logger import setup_logger

logger = setup_logger("market_analyzer")


class MarketAnalyzer:
    """
    시장 분석 엔진

    - 다중 타임프레임 데이터에 지표 적용
    - 시장 상태 평가 (추세, 변동성, 거래량)
    - 진입 회피 조건 필터링
    - 최종 매매 신호 생성
    """

    def __init__(self, data_fetcher: DataFetcher):
        self._data = data_fetcher
        self._last_analysis: Optional[Dict[str, Any]] = None

    @property
    def last_analysis(self) -> Optional[Dict[str, Any]]:
        return self._last_analysis

    async def analyze(self) -> Signal:
        """
        전체 시장 분석 실행

        1. 캔들 데이터 새로고침
        2. 지표 계산
        3. 진입 회피 조건 확인
        4. 매매 신호 생성

        Returns:
            Signal 객체
        """
        logger.info("📊 시장 분석 시작...")

        # 1. 4시간봉 + 1일봉 새로고침
        await self._data.refresh_candles("4h")
        await self._data.refresh_candles("1d")

        df_4h = self._data.get_candles("4h")
        df_1d = self._data.get_candles("1d")

        if df_4h is None or len(df_4h) < 50:
            logger.warning("4시간봉 데이터 부족 (최소 50개 필요)")
            return Signal(signal_type=SignalType.NO_SIGNAL, reasons=["데이터 부족"])

        # 2. 지표 계산
        df_4h = prepare_dataframe(df_4h)
        if df_1d is not None and len(df_1d) > 50:
            df_1d = prepare_dataframe(df_1d)

        # 3. 시장 상태 평가
        market_state = self._evaluate_market_state(df_4h)
        logger.info(f"   시장 상태: {market_state}")

        # 4. 진입 회피 조건 확인
        avoidance = self._check_avoidance_conditions(df_4h, df_1d)
        if avoidance["should_avoid"]:
            logger.warning(f"   ⛔ 진입 회피: {avoidance['reasons']}")
            self._last_analysis = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "market_state": market_state,
                "avoidance": avoidance,
                "signal": "no_signal",
                "signal_reasons": avoidance["reasons"],
            }
            return Signal(
                signal_type=SignalType.NO_SIGNAL,
                reasons=avoidance["reasons"],
            )

        # 5. 매매 신호 생성
        long_signal = check_long_entry(df_4h, df_1d)
        short_signal = check_short_entry(df_4h, df_1d)

        # 더 강한 신호 선택
        if long_signal.signal_type == SignalType.LONG and short_signal.signal_type == SignalType.SHORT:
            signal = long_signal if long_signal.confidence >= short_signal.confidence else short_signal
        elif long_signal.signal_type == SignalType.LONG:
            signal = long_signal
        elif short_signal.signal_type == SignalType.SHORT:
            signal = short_signal
        else:
            signal = long_signal  # NO_SIGNAL (reasons 포함)

        # 분석 결과 저장
        self._last_analysis = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "market_state": market_state,
            "avoidance": avoidance,
            "signal": signal.signal_type.value,
            "signal_confidence": signal.confidence,
            "signal_reasons": signal.reasons,
            "mandatory_met": signal.mandatory_met,
            "additional_met": signal.additional_met,
            "stop_loss": signal.stop_loss,
            "take_profit_1": signal.take_profit_1,
            "current_price": self._data.current_price,
        }

        if signal.signal_type != SignalType.NO_SIGNAL:
            logger.info(f"   📍 신호: {signal.signal_type.value} | 신뢰도: {signal.confidence:.0%}")
        else:
            logger.info(f"   📍 신호 없음 | 필수: {signal.mandatory_met}/4, 추가: {signal.additional_met}")

        return signal

    async def check_exit_signal(self, position_side: str) -> Signal:
        """
        포지션 청산 신호 확인

        Args:
            position_side: 'long' 또는 'short'
        """
        df_4h = self._data.get_candles("4h")
        if df_4h is None or len(df_4h) < 30:
            return Signal(signal_type=SignalType.NO_SIGNAL)

        df_4h = prepare_dataframe(df_4h)
        return check_close_signal(df_4h, position_side)

    def _evaluate_market_state(self, df: pd.DataFrame) -> Dict[str, Any]:
        """시장 상태 평가"""
        current_price = df["close"].iloc[-1]
        ema_50 = df["ema_50"].iloc[-1] if "ema_50" in df.columns else current_price
        ema_200 = df["ema_200"].iloc[-1] if "ema_200" in df.columns else current_price
        rsi = df["rsi"].iloc[-1] if "rsi" in df.columns else 50

        # 추세 판별
        if current_price > ema_50 > ema_200:
            trend = "bullish"
        elif current_price < ema_50 < ema_200:
            trend = "bearish"
        else:
            trend = "neutral"

        # 변동성 (최근 24시간 = 6개 4시간봉)
        recent = df.tail(6)
        volatility = ((recent["high"].max() - recent["low"].min()) / current_price) * 100

        # 평균 변동성 (60개 캔들 = 10일)
        if len(df) >= 60:
            avg_ranges = ((df["high"] - df["low"]) / df["close"] * 100).tail(60).mean()
        else:
            avg_ranges = volatility

        return {
            "trend": trend,
            "price": current_price,
            "ema_50": ema_50,
            "ema_200": ema_200,
            "rsi": round(rsi, 1),
            "volatility_24h": round(volatility, 2),
            "avg_volatility": round(avg_ranges, 2),
        }

    def _check_avoidance_conditions(
        self,
        df_4h: pd.DataFrame,
        df_1d: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """
        진입 회피 조건 확인

        1. 24시간 변동성 > 평균 3배 (급등락)
        2. 1일봉 EMA 50-200 사이 (불확실 구간)
        3. 거래량 < 14MA의 50%
        """
        reasons = []
        current_price = df_4h["close"].iloc[-1]

        # 1. 극단적 변동성
        recent = df_4h.tail(6)
        range_pct = ((recent["high"].max() - recent["low"].min()) / current_price) * 100
        if len(df_4h) >= 60:
            avg_range = ((df_4h["high"] - df_4h["low"]) / df_4h["close"] * 100).tail(60).mean()
            if range_pct > avg_range * EXTREME_VOLATILITY_MULTIPLIER:
                reasons.append(f"변동성 과대 ({range_pct:.1f}% > 평균 {avg_range:.1f}% x {EXTREME_VOLATILITY_MULTIPLIER})")

        # 2. 불확실 구간 (EMA 50-200 사이)
        if df_1d is not None and "ema_50" in df_1d.columns and "ema_200" in df_1d.columns:
            ema50 = df_1d["ema_50"].iloc[-1]
            ema200 = df_1d["ema_200"].iloc[-1]
            d_price = df_1d["close"].iloc[-1]
            if min(ema50, ema200) < d_price < max(ema50, ema200):
                reasons.append("1일봉 EMA50-200 사이 (불확실 구간)")

        # 3. 거래량 부족
        if is_volume_too_low(df_4h, threshold=LOW_VOLUME_THRESHOLD):
            reasons.append("거래량 < 14MA의 50%")

        return {
            "should_avoid": len(reasons) > 0,
            "reasons": reasons,
        }
