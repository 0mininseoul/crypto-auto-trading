"""
Bitget WebSocket 클라이언트 (Public API V2)
실시간 시세, 체결, 캔들 스트리밍
"""
import asyncio
import json
import time
from typing import Callable, Optional, Dict, Any, List

import aiohttp

from src.config.constants import (
    BITGET_WS_PUBLIC_URL,
    SYMBOL,
    WS_PING_INTERVAL,
    WS_RECONNECT_DELAY,
    WS_RECONNECT_MAX_DELAY,
    get_active_symbol,
    get_active_product_type,
)
from src.utils.logger import setup_logger

logger = setup_logger("websocket")


class BitgetWebSocket:
    """Bitget Public WebSocket V2 클라이언트"""

    def __init__(self, url: str = BITGET_WS_PUBLIC_URL):
        self._url = url
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._callbacks: Dict[str, List[Callable]] = {}
        self._reconnect_delay = WS_RECONNECT_DELAY
        self._ping_task: Optional[asyncio.Task] = None
        self._listen_task: Optional[asyncio.Task] = None

    @property
    def is_connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    def on(self, channel: str, callback: Callable):
        """
        이벤트 콜백 등록

        Args:
            channel: 'ticker', 'trade', 'candle1m' 등
            callback: async def handler(data: dict)
        """
        if channel not in self._callbacks:
            self._callbacks[channel] = []
        self._callbacks[channel].append(callback)

    async def connect(self):
        """WebSocket 연결"""
        if self._session is None:
            self._session = aiohttp.ClientSession()

        try:
            self._ws = await self._session.ws_connect(
                self._url,
                heartbeat=WS_PING_INTERVAL,
                timeout=30,
            )
            self._running = True
            self._reconnect_delay = WS_RECONNECT_DELAY
            logger.info(f"✅ WebSocket 연결됨: {self._url}")

            # Ping 태스크 시작
            self._ping_task = asyncio.create_task(self._ping_loop())

        except Exception as e:
            logger.error(f"WebSocket 연결 실패: {e}")
            raise

    async def subscribe(self, channels: List[Dict[str, str]]):
        """
        채널 구독

        Args:
            channels: [{"instType": "USDT-FUTURES", "channel": "ticker", "instId": "BTCUSDT"}, ...]
        """
        if not self.is_connected:
            await self.connect()

        msg = {
            "op": "subscribe",
            "args": channels,
        }
        await self._ws.send_json(msg)
        logger.info(f"구독 요청: {[c['channel'] for c in channels]}")

    async def subscribe_ticker(self, symbol: str = None):
        """실시간 시세 구독"""
        if symbol is None:
            symbol = get_active_symbol()
        await self.subscribe([{
            "instType": get_active_product_type(),
            "channel": "ticker",
            "instId": symbol,
        }])

    async def subscribe_trades(self, symbol: str = None):
        """실시간 체결 구독"""
        if symbol is None:
            symbol = get_active_symbol()
        await self.subscribe([{
            "instType": get_active_product_type(),
            "channel": "trade",
            "instId": symbol,
        }])

    async def subscribe_candles(self, symbol: str = None, interval: str = "1m"):
        """실시간 캔들 구독"""
        if symbol is None:
            symbol = get_active_symbol()
        await self.subscribe([{
            "instType": get_active_product_type(),
            "channel": f"candle{interval}",
            "instId": symbol,
        }])

    async def listen(self):
        """메시지 수신 루프 (메인 루프에서 호출)"""
        while self._running:
            try:
                if not self.is_connected:
                    await self._reconnect()
                    continue

                msg = await self._ws.receive(timeout=WS_PING_INTERVAL + 10)

                if msg.type == aiohttp.WSMsgType.TEXT:
                    # Bitget pong 응답 처리 (JSON 아님)
                    if msg.data == "pong":
                        continue
                    try:
                        data = json.loads(msg.data)
                        await self._handle_message(data)
                    except json.JSONDecodeError:
                        logger.debug(f"JSON 파싱 스킵 (비JSON 메시지): {msg.data[:50]}")

                elif msg.type == aiohttp.WSMsgType.PING:
                    await self._ws.pong()

                elif msg.type == aiohttp.WSMsgType.PONG:
                    pass  # 정상

                elif msg.type in (
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                    aiohttp.WSMsgType.CLOSING,
                ):
                    logger.warning(f"WebSocket 연결 끊김: {msg.type}")
                    await self._reconnect()

            except asyncio.TimeoutError:
                logger.warning("WebSocket 수신 타임아웃 - 재연결 시도")
                await self._reconnect()
            except asyncio.CancelledError:
                logger.info("WebSocket 리스닝 취소됨")
                break
            except Exception as e:
                logger.error(f"WebSocket 오류: {e}")
                await self._reconnect()

    async def _handle_message(self, data: Dict[str, Any]):
        """메시지 분기 처리"""
        # 구독 확인 응답
        if "event" in data:
            event = data["event"]
            if event == "subscribe":
                logger.info(f"구독 성공: {data.get('arg', {}).get('channel', 'unknown')}")
            elif event == "error":
                logger.error(f"구독 오류: {data}")
            return

        # 데이터 메시지
        if "arg" in data and "data" in data:
            channel = data["arg"].get("channel", "")
            callbacks = self._callbacks.get(channel, [])

            # candle* 채널은 공통 핸들러도 호출
            if channel.startswith("candle") and "candle" in self._callbacks:
                callbacks = callbacks + self._callbacks.get("candle", [])

            for callback in callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(data)
                    else:
                        callback(data)
                except Exception as e:
                    logger.error(f"콜백 오류 ({channel}): {e}")

    async def _ping_loop(self):
        """주기적 Ping 전송"""
        while self._running and self.is_connected:
            try:
                await asyncio.sleep(WS_PING_INTERVAL)
                if self.is_connected:
                    await self._ws.send_str("ping")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Ping 전송 실패: {e}")
                break

    async def _reconnect(self):
        """자동 재연결 (Exponential Backoff)"""
        if self._ws and not self._ws.closed:
            try:
                await self._ws.close()
            except Exception:
                pass

        logger.info(f"🔄 {self._reconnect_delay}초 후 재연결 시도...")
        await asyncio.sleep(self._reconnect_delay)

        # Exponential backoff
        self._reconnect_delay = min(
            self._reconnect_delay * 2, WS_RECONNECT_MAX_DELAY
        )

        try:
            await self.connect()
            # 기존 구독 채널 재구독
            # (콜백이 등록된 채널 기반으로 자동 재구독)
            channels = []
            for channel_name in self._callbacks.keys():
                if channel_name == "candle":
                    continue  # 일반 핸들러, 실제 채널 아님
                inst_type = get_active_product_type()
                channels.append({
                    "instType": inst_type,
                    "channel": channel_name,
                    "instId": get_active_symbol(),
                })
            if channels:
                await self.subscribe(channels)
                logger.info("✅ 재구독 완료")
        except Exception as e:
            logger.error(f"재연결 실패: {e}")

    async def stop(self):
        """WebSocket 종료"""
        self._running = False

        if self._ping_task:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass

        if self._ws and not self._ws.closed:
            await self._ws.close()

        if self._session and not self._session.closed:
            await self._session.close()

        logger.info("WebSocket 종료 완료")
