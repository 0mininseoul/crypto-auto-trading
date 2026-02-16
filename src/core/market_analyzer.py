"""
시장 분석 엔진 (Market Analyzer)
지표 계산 + 시장 상태 평가 + 진입 회피 조건 + 신호 생성

v2.0 — 15분봉 데이트레이딩
- 메인: 15분봉 (신호 생성)
- 추세 확인: 1시간봉 (상위 TF 필터)
- 타이밍: 5분봉 (추가 확인)
"""
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from src.utils.helpers import kst_now

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
        전체 시장 분석 실행 (15분봉 데이트레이딩)

        1. 15분봉 + 1시간봉 + 5분봉 캔들 새로고침
        2. 지표 계산
        3. 진입 회피 조건 확인
        4. 매매 신호 생성

        Returns:
            Signal 객체
        """
        logger.info("📊 시장 분석 시작...")

        # 1. 멀티 타임프레임 캔들 새로고침
        await self._data.refresh_candles("15m")
        await self._data.refresh_candles("1h")
        await self._data.refresh_candles("5m")

        df_15m = self._data.get_candles("15m")
        df_1h = self._data.get_candles("1h")
        df_5m = self._data.get_candles("5m")

        if df_15m is None or len(df_15m) < 50:
            logger.warning("15분봉 데이터 부족 (최소 50개 필요)")
            return Signal(signal_type=SignalType.NO_SIGNAL, reasons=["데이터 부족"])

        # 2. 지표 계산
        df_15m = prepare_dataframe(df_15m)
        if df_1h is not None and len(df_1h) > 50:
            df_1h = prepare_dataframe(df_1h)
        if df_5m is not None and len(df_5m) > 30:
            df_5m = prepare_dataframe(df_5m)

        # 3. 시장 상태 평가
        market_state = self._evaluate_market_state(df_15m)
        logger.info(f"   시장 상태: {market_state}")

        # 4. 진입 회피 조건 확인
        avoidance = self._check_avoidance_conditions(df_15m, df_1h)
        if avoidance["should_avoid"]:
            logger.warning(f"   ⛔ 진입 회피: {avoidance['reasons']}")
            self._last_analysis = {
                "timestamp": kst_now().isoformat(),
                "market_state": market_state,
                "avoidance": avoidance,
                "signal": "no_signal",
                "signal_reasons": avoidance["reasons"],
            }
            return Signal(
                signal_type=SignalType.NO_SIGNAL,
                reasons=avoidance["reasons"],
            )

        # 5. 매매 신호 생성 (15분봉 메인 + 1시간봉 추세 + 5분봉 타이밍)
        long_signal = check_long_entry(df_15m, df_1h, df_5m)
        short_signal = check_short_entry(df_15m, df_1h, df_5m)

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
            "timestamp": kst_now().isoformat(),
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
            logger.info(f"   📍 신호 없음 | 필수: {signal.mandatory_met}/3, 추가: {signal.additional_met}")

        return signal

    async def check_exit_signal(self, position_side: str) -> Signal:
        """
        포지션 청산 신호 확인 (15분봉 기반)

        Args:
            position_side: 'long' 또는 'short'
        """
        df_15m = self._data.get_candles("15m")
        if df_15m is None or len(df_15m) < 30:
            return Signal(signal_type=SignalType.NO_SIGNAL)

        df_15m = prepare_dataframe(df_15m)
        return check_close_signal(df_15m, position_side)

    def _evaluate_market_state(self, df: pd.DataFrame) -> Dict[str, Any]:
        """시장 상태 평가 (15분봉 기준)"""
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

        # 변동성 (최근 4시간 = 16개 15분봉)
        recent = df.tail(16)
        volatility = ((recent["high"].max() - recent["low"].min()) / current_price) * 100

        # 평균 변동성 (96개 캔들 = 24시간)
        if len(df) >= 96:
            avg_ranges = ((df["high"] - df["low"]) / df["close"] * 100).tail(96).mean()
        else:
            avg_ranges = volatility

        return {
            "trend": trend,
            "price": current_price,
            "ema_50": ema_50,
            "ema_200": ema_200,
            "rsi": round(rsi, 1),
            "volatility_4h": round(volatility, 2),
            "avg_volatility": round(avg_ranges, 2),
        }

    def _check_avoidance_conditions(
        self,
        df_15m: pd.DataFrame,
        df_1h: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """
        진입 회피 조건 확인 (15분봉 기준)

        1. 최근 4시간 변동성 > 평균 3배 (급등락)
        2. 1시간봉 EMA 50-200 사이 (불확실 구간)
        3. 거래량 < 14MA의 50%
        """
        reasons = []
        current_price = df_15m["close"].iloc[-1]

        # 1. 극단적 변동성 (최근 4시간 = 16개 15분봉)
        recent = df_15m.tail(16)
        range_pct = ((recent["high"].max() - recent["low"].min()) / current_price) * 100
        if len(df_15m) >= 96:
            avg_range = ((df_15m["high"] - df_15m["low"]) / df_15m["close"] * 100).tail(96).mean()
            if range_pct > avg_range * EXTREME_VOLATILITY_MULTIPLIER:
                reasons.append(f"변동성 과대 ({range_pct:.1f}% > 평균 {avg_range:.1f}% x {EXTREME_VOLATILITY_MULTIPLIER})")

        # 2. 불확실 구간 (1시간봉 EMA 50-200 사이)
        if df_1h is not None and "ema_50" in df_1h.columns and "ema_200" in df_1h.columns:
            ema50 = df_1h["ema_50"].iloc[-1]
            ema200 = df_1h["ema_200"].iloc[-1]
            h_price = df_1h["close"].iloc[-1]
            if min(ema50, ema200) < h_price < max(ema50, ema200):
                reasons.append("1시간봉 EMA50-200 사이 (불확실 구간)")

        # 3. 거래량 부족
        if is_volume_too_low(df_15m, threshold=LOW_VOLUME_THRESHOLD):
            reasons.append("거래량 < 14MA의 50%")

        return {
            "should_avoid": len(reasons) > 0,
            "reasons": reasons,
        }
