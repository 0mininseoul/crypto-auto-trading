"""
AI 차트 분석기 (Chart Analyzer)
Gemini API를 사용한 실시간 차트 분석 + 자체 학습 시스템

모델: gemini-3-flash-preview
"""
import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple

import google.generativeai as genai
import pandas as pd

from src.config.settings import get_settings
from src.exchange.data_fetcher import DataFetcher
from src.exchange.bitget_client import BitgetClient
from src.indicators.signals import prepare_dataframe, SignalType
from src.ai.prompts import (
    get_system_prompt,
    build_full_prompt,
    build_review_prompt,
    add_trade_review,
    add_insight,
    add_pattern,
    load_learning_history,
)
from src.utils.logger import setup_logger
from src.utils.helpers import kst_now

logger = setup_logger("chart_analyzer")

# 싱글톤
_chart_analyzer: Optional["ChartAnalyzer"] = None

# 캐시 설정
CACHE_TTL_SECONDS = 180  # 3분


class ChartAnalyzer:
    """
    AI 기반 차트 분석기

    - 실시간 시장 데이터 수집
    - Gemini API로 분석 요청
    - 결과 캐싱 (3분)
    - 자체 학습 시스템 (복기 결과 축적)
    """

    def __init__(
        self,
        data_fetcher: DataFetcher,
        exchange_client: BitgetClient,
    ):
        self._data = data_fetcher
        self._exchange = exchange_client
        self._settings = get_settings()
        self._model: Optional[genai.GenerativeModel] = None
        self._cache: Dict[str, Tuple[datetime, str]] = {}
        self._last_entry_analysis: Optional[str] = None  # 진입 시 분석 저장
        self._last_entry_market: Optional[Dict[str, Any]] = None

        self._initialize_gemini()

    def _initialize_gemini(self):
        """Gemini API 초기화"""
        api_key = self._settings.gemini_api_key
        if not api_key:
            logger.warning("GEMINI_API_KEY 미설정 - AI 분석 비활성화")
            return

        try:
            genai.configure(api_key=api_key)
            self._model = genai.GenerativeModel(
                model_name="gemini-3-flash-preview",
                system_instruction=get_system_prompt(),
            )
            logger.info("Gemini API 초기화 완료 (gemini-3-flash-preview)")
        except Exception as e:
            logger.error(f"Gemini API 초기화 실패: {e}")
            self._model = None

    @property
    def is_available(self) -> bool:
        """AI 분석 사용 가능 여부"""
        return self._model is not None

    async def analyze(
        self,
        position: Optional[Dict[str, Any]] = None,
        signal_info: Optional[Dict[str, Any]] = None,
        analysis_type: str = "general",
        force_refresh: bool = False,
    ) -> str:
        """
        현재 차트 분석 실행

        Args:
            position: 현재 포지션 정보 (없으면 None)
            signal_info: 현재 시그널 정보 (MarketAnalyzer에서)
            analysis_type: "general", "entry", "exit"
            force_refresh: 캐시 무시 여부

        Returns:
            AI 분석 결과 텍스트
        """
        if not self.is_available:
            return "AI 분석을 사용할 수 없습니다. GEMINI_API_KEY를 확인하세요."

        # 캐시 확인
        cache_key = f"{analysis_type}_{position is not None}"
        if not force_refresh and cache_key in self._cache:
            cached_time, cached_result = self._cache[cache_key]
            if datetime.now() - cached_time < timedelta(seconds=CACHE_TTL_SECONDS):
                logger.debug("캐시된 분석 결과 반환")
                return cached_result

        try:
            # 시장 데이터 수집
            market_data = await self._collect_market_data()
            if not market_data:
                return "시장 데이터 수집 실패"

            # 프롬프트 생성
            prompt = build_full_prompt(
                current_price=market_data["current_price"],
                df_15m_summary=market_data["df_15m"],
                df_1h_summary=market_data["df_1h"],
                df_5m_summary=market_data["df_5m"],
                volume_info=market_data["volume"],
                position=position,
                signal_info=signal_info,
                analysis_type=analysis_type,
            )

            # Gemini API 호출
            response = await asyncio.to_thread(
                self._model.generate_content,
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=800,
                ),
            )

            result = response.text.strip()

            # 캐시 저장
            self._cache[cache_key] = (datetime.now(), result)

            # 진입 분석인 경우 저장 (복기용)
            if analysis_type == "entry":
                self._last_entry_analysis = result
                self._last_entry_market = market_data

            logger.info(f"AI 분석 완료 ({analysis_type})")
            return result

        except Exception as e:
            logger.error(f"AI 분석 실패: {e}")
            return f"AI 분석 중 오류 발생: {str(e)[:100]}"

    async def analyze_for_entry(
        self,
        signal_info: Dict[str, Any],
    ) -> str:
        """진입 시 분석 (자동 호출용)"""
        return await self.analyze(
            position=None,
            signal_info=signal_info,
            analysis_type="entry",
            force_refresh=True,
        )

    async def analyze_for_exit(
        self,
        trade_data: Dict[str, Any],
    ) -> str:
        """
        청산 시 복기 분석 + 학습

        Args:
            trade_data: 완료된 거래 정보
        """
        if not self.is_available:
            return "AI 분석을 사용할 수 없습니다."

        try:
            # 현재 시장 데이터 수집
            market_at_exit = await self._collect_market_data()

            # 복기 프롬프트 생성
            prompt = build_review_prompt(
                trade_data=trade_data,
                entry_analysis=self._last_entry_analysis or "",
                market_at_entry=self._last_entry_market or {},
                market_at_exit=market_at_exit or {},
            )

            # Gemini API 호출
            response = await asyncio.to_thread(
                self._model.generate_content,
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.2,
                    max_output_tokens=1000,
                ),
            )

            result = response.text.strip()

            # 학습 데이터 추출 및 저장
            await self._process_review_result(trade_data, result)

            # 진입 분석 초기화
            self._last_entry_analysis = None
            self._last_entry_market = None

            logger.info("거래 복기 및 학습 완료")
            return result

        except Exception as e:
            logger.error(f"복기 분석 실패: {e}")
            return f"복기 분석 중 오류 발생: {str(e)[:100]}"

    async def _process_review_result(
        self,
        trade_data: Dict[str, Any],
        review_text: str,
    ):
        """복기 결과에서 학습 데이터 추출 및 저장"""
        try:
            # JSON 블록 추출
            json_match = re.search(r'```json\s*(.*?)\s*```', review_text, re.DOTALL)
            if json_match:
                learning_data = json.loads(json_match.group(1))

                # 거래 결과 판정
                pnl = trade_data.get("pnl", 0)
                if pnl > 0:
                    result = "win"
                elif pnl < 0:
                    result = "loss"
                else:
                    result = "breakeven"

                # 교훈 저장
                lessons = learning_data.get("lessons", [])
                add_trade_review(
                    trade_data=trade_data,
                    analysis_before=self._last_entry_analysis or "",
                    result=result,
                    lessons_learned=lessons,
                )

                # 패턴 저장
                pattern_type = learning_data.get("pattern_type")
                pattern_desc = learning_data.get("pattern_description")
                if pattern_type and pattern_desc:
                    add_pattern(pattern_type, {"description": pattern_desc})

                # 주요 인사이트 추가
                if lessons:
                    add_insight(lessons[0], category=result)

                logger.info(f"학습 데이터 저장: {result}, 교훈 {len(lessons)}개")

        except json.JSONDecodeError:
            logger.warning("복기 결과에서 JSON 추출 실패 - 학습 건너뜀")
        except Exception as e:
            logger.error(f"학습 데이터 처리 실패: {e}")

    async def _collect_market_data(self) -> Optional[Dict[str, Any]]:
        """시장 데이터 수집 및 요약"""
        try:
            # 캔들 새로고침
            await self._data.refresh_candles("15m")
            await self._data.refresh_candles("1h")
            await self._data.refresh_candles("5m")

            df_15m = self._data.get_candles("15m")
            df_1h = self._data.get_candles("1h")
            df_5m = self._data.get_candles("5m")

            if df_15m is None or len(df_15m) < 50:
                return None

            # 지표 계산
            df_15m = prepare_dataframe(df_15m)
            if df_1h is not None and len(df_1h) > 50:
                df_1h = prepare_dataframe(df_1h)
            if df_5m is not None and len(df_5m) > 30:
                df_5m = prepare_dataframe(df_5m)

            current_price = self._data.current_price

            return {
                "current_price": current_price,
                "df_15m": self._summarize_df(df_15m, "15m"),
                "df_1h": self._summarize_df(df_1h, "1h") if df_1h is not None else {},
                "df_5m": self._summarize_df(df_5m, "5m") if df_5m is not None else {},
                "volume": self._get_volume_info(df_15m),
            }

        except Exception as e:
            logger.error(f"시장 데이터 수집 실패: {e}")
            return None

    def _summarize_df(self, df: pd.DataFrame, timeframe: str) -> Dict[str, Any]:
        """DataFrame 요약"""
        if df is None or len(df) < 2:
            return {}

        idx = -2  # 마감된 캔들 기준
        row = df.iloc[idx]

        summary = {
            "ema_9": row.get("ema_9", 0),
            "ema_21": row.get("ema_21", 0),
            "ema_50": row.get("ema_50", 0),
            "ema_200": row.get("ema_200", 0) if "ema_200" in df.columns else 0,
            "rsi": row.get("rsi", 50),
        }

        # MACD
        if "macd_hist" in df.columns:
            hist = row.get("macd_hist", 0)
            prev_hist = df.iloc[idx - 1].get("macd_hist", 0) if len(df) > 2 else 0
            summary["macd_hist"] = hist
            summary["macd_direction"] = "상승" if hist > prev_hist else "하락"

        # 추세 판단
        price = row["close"]
        ema_50 = summary.get("ema_50", price)
        ema_200 = summary.get("ema_200", price)
        if price > ema_50 > ema_200:
            summary["trend"] = "상승 (강세)"
        elif price < ema_50 < ema_200:
            summary["trend"] = "하락 (약세)"
        else:
            summary["trend"] = "중립/혼조"

        # EMA 정배열 여부 (5분봉용)
        if timeframe == "5m":
            summary["ema_aligned"] = summary["ema_9"] > summary["ema_21"]

        # 캔들 패턴 (간단히)
        body = abs(row["close"] - row["open"])
        upper_wick = row["high"] - max(row["close"], row["open"])
        lower_wick = min(row["close"], row["open"]) - row["low"]

        if lower_wick > body * 2 and upper_wick < body * 0.5:
            summary["candle_pattern"] = "해머형 (반등 가능)"
        elif upper_wick > body * 2 and lower_wick < body * 0.5:
            summary["candle_pattern"] = "슈팅스타 (하락 가능)"
        elif row["close"] > row["open"] and body > (row["high"] - row["low"]) * 0.7:
            summary["candle_pattern"] = "강한 양봉"
        elif row["close"] < row["open"] and body > (row["high"] - row["low"]) * 0.7:
            summary["candle_pattern"] = "강한 음봉"
        else:
            summary["candle_pattern"] = "보통"

        return summary

    def _get_volume_info(self, df: pd.DataFrame) -> Dict[str, Any]:
        """거래량 정보"""
        if df is None or "volume_ma" not in df.columns:
            return {}

        idx = -2
        row = df.iloc[idx]
        vol = row["volume"]
        vol_ma = row["volume_ma"]

        # OBV 추세
        obv_trend = "N/A"
        if "obv" in df.columns and len(df) > 10:
            obv_recent = df["obv"].iloc[-10:].values
            if obv_recent[-1] > obv_recent[0]:
                obv_trend = "상승"
            else:
                obv_trend = "하락"

        return {
            "current": vol,
            "ma_14": vol_ma,
            "ratio": vol / vol_ma if vol_ma > 0 else 0,
            "obv_trend": obv_trend,
        }

    def get_learning_stats(self) -> Dict[str, Any]:
        """학습 통계 반환"""
        history = load_learning_history()
        stats = history.get("stats", {})
        total = stats.get("total_analyses", 0)
        accurate = stats.get("accurate_predictions", 0)

        return {
            "total_reviews": total,
            "wins": accurate,
            "win_rate": accurate / total if total > 0 else 0,
            "insights_count": len(history.get("insights", [])),
            "patterns_count": sum(
                len(v) for v in history.get("patterns", {}).values()
            ),
            "last_updated": stats.get("last_updated"),
        }


def get_chart_analyzer() -> Optional[ChartAnalyzer]:
    """ChartAnalyzer 싱글톤 반환 (초기화 전이면 None)"""
    global _chart_analyzer
    return _chart_analyzer


def init_chart_analyzer(
    data_fetcher: DataFetcher,
    exchange_client: BitgetClient,
) -> ChartAnalyzer:
    """ChartAnalyzer 초기화"""
    global _chart_analyzer
    _chart_analyzer = ChartAnalyzer(data_fetcher, exchange_client)
    return _chart_analyzer
