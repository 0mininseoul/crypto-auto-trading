"""
데이터 수집 및 캔들 관리
REST로 히스토리 로드 + WebSocket으로 실시간 업데이트
"""
import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional, Callable, List

import pandas as pd

from src.exchange.bitget_client import BitgetClient
from src.exchange.websocket_client import BitgetWebSocket
from src.config.constants import CCXT_SYMBOL, SYMBOL, TIMEFRAMES
from src.utils.logger import setup_logger
from src.utils.helpers import timestamp_to_datetime

logger = setup_logger("data_fetcher")


class DataFetcher:
    """
    캔들 데이터 관리자

    - 초기화 시 REST API로 히스토리 로드
    - 이후 WebSocket으로 실시간 업데이트
    """

    def __init__(self, rest_client: BitgetClient, ws_client: Optional[BitgetWebSocket] = None):
        self._rest = rest_client
        self._ws = ws_client
        self._candles: Dict[str, pd.DataFrame] = {}  # timeframe → DataFrame
        self._current_price: float = 0.0
        self._price_callbacks: List[Callable] = []

    @property
    def current_price(self) -> float:
        """현재 가격"""
        return self._current_price

    def get_candles(self, timeframe: str = "4h") -> Optional[pd.DataFrame]:
        """
        캔들 데이터 반환

        Args:
            timeframe: '1m', '15m', '1h', '4h', '1d'

        Returns:
            DataFrame with columns: [timestamp, open, high, low, close, volume]
        """
        return self._candles.get(timeframe)

    def on_price_update(self, callback: Callable):
        """가격 업데이트 콜백 등록"""
        self._price_callbacks.append(callback)

    async def initialize(self, timeframes: Optional[List[str]] = None):
        """
        초기화: REST API로 히스토리 캔들 로드

        Args:
            timeframes: 로드할 타임프레임 목록 (기본: 모든 타임프레임)
        """
        if timeframes is None:
            timeframes = list(TIMEFRAMES.values())

        logger.info(f"📊 캔들 데이터 초기화 시작: {timeframes}")

        for tf in timeframes:
            try:
                ohlcv = await self._rest.get_ohlcv(
                    symbol=CCXT_SYMBOL,
                    timeframe=tf,
                    limit=200,
                )
                df = self._ohlcv_to_dataframe(ohlcv)
                self._candles[tf] = df
                logger.info(f"  ✅ {tf}: {len(df)}개 캔들 로드")
            except Exception as e:
                logger.error(f"  ❌ {tf} 캔들 로드 실패: {e}")

        # 현재 가격 초기화
        try:
            ticker = await self._rest.get_ticker()
            self._current_price = ticker["last"]
            logger.info(f"  💰 현재 가격: ${self._current_price:,.2f}")
        except Exception as e:
            logger.error(f"  ❌ 현재 가격 로드 실패: {e}")

    async def start_realtime(self):
        """WebSocket 실시간 업데이트 시작"""
        if not self._ws:
            logger.warning("WebSocket 클라이언트 없음 — REST 전용 모드")
            return

        # 콜백 등록
        self._ws.on("ticker", self._on_ticker)
        self._ws.on("candle1m", self._on_candle)

        # WebSocket 연결 및 구독
        await self._ws.connect()
        await self._ws.subscribe_ticker(SYMBOL)
        await self._ws.subscribe_candles(SYMBOL, "1m")

        logger.info("🔴 실시간 데이터 수신 시작")

    async def close(self):
        """리소스 정리"""
        if self._ws:
            await self._ws.stop()

    async def _on_ticker(self, data: dict):
        """실시간 시세 수신 핸들러"""
        try:
            ticker_data = data.get("data", [{}])[0]
            last_price = float(ticker_data.get("lastPr", 0))
            if last_price > 0:
                self._current_price = last_price
                # 콜백 호출
                for cb in self._price_callbacks:
                    try:
                        if asyncio.iscoroutinefunction(cb):
                            await cb(last_price)
                        else:
                            cb(last_price)
                    except Exception as e:
                        logger.error(f"가격 콜백 오류: {e}")
        except Exception as e:
            logger.error(f"Ticker 처리 오류: {e}")

    async def _on_candle(self, data: dict):
        """실시간 1분봉 업데이트 핸들러"""
        try:
            candle_data = data.get("data", [])
            if not candle_data:
                return

            for c in candle_data:
                # Bitget candle format: [ts, open, high, low, close, vol, volCcy]
                ts = int(c[0])
                new_row = {
                    "timestamp": timestamp_to_datetime(ts),
                    "open": float(c[1]),
                    "high": float(c[2]),
                    "low": float(c[3]),
                    "close": float(c[4]),
                    "volume": float(c[5]),
                }

                # 1분봉 DataFrame 업데이트
                if "1m" in self._candles:
                    df = self._candles["1m"]
                    dt = new_row["timestamp"]
                    # 기존 캔들 업데이트 또는 새 캔들 추가
                    mask = df["timestamp"] == dt
                    if mask.any():
                        idx = df[mask].index[0]
                        for col in ["open", "high", "low", "close", "volume"]:
                            df.at[idx, col] = new_row[col]
                    else:
                        new_df = pd.DataFrame([new_row])
                        self._candles["1m"] = pd.concat(
                            [df, new_df], ignore_index=True
                        ).tail(500)  # 최근 500개만 유지
        except Exception as e:
            logger.error(f"캔들 업데이트 오류: {e}")

    async def refresh_candles(self, timeframe: str):
        """특정 타임프레임 캔들 새로고침 (REST)"""
        try:
            ohlcv = await self._rest.get_ohlcv(
                symbol=CCXT_SYMBOL,
                timeframe=timeframe,
                limit=200,
            )
            df = self._ohlcv_to_dataframe(ohlcv)
            self._candles[timeframe] = df
            logger.debug(f"캔들 새로고침: {timeframe} x{len(df)}")
        except Exception as e:
            logger.error(f"캔들 새로고침 실패 ({timeframe}): {e}")

    @staticmethod
    def _ohlcv_to_dataframe(ohlcv: list) -> pd.DataFrame:
        """ccxt OHLCV → pandas DataFrame"""
        df = pd.DataFrame(
            ohlcv,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        return df
