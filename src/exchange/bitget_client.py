"""
Bitget REST API 클라이언트 (Async ccxt)
잔고 조회, OHLCV, 주문, 포지션 관리
"""
import asyncio
from typing import Optional, List, Dict, Any

import ccxt.async_support as ccxt

from src.config.settings import get_settings
from src.config.constants import CCXT_SYMBOL, MARGIN_MODE, DEFAULT_LEVERAGE
from src.utils.logger import setup_logger

logger = setup_logger("bitget_client")


class BitgetClient:
    """Bitget 거래소 비동기 클라이언트"""

    def __init__(self):
        settings = get_settings()
        self._exchange: Optional[ccxt.bitget] = None
        self._settings = settings

    async def _get_exchange(self) -> ccxt.bitget:
        """ccxt 거래소 인스턴스 (lazy init)"""
        if self._exchange is None:
            config = {
                "apiKey": self._settings.bitget_api_key,
                "secret": self._settings.bitget_secret_key,
                "password": self._settings.bitget_passphrase,
                "options": {
                    "defaultType": "swap",         # 무기한 선물
                    "defaultSubType": "linear",    # USDT-M
                },
                "enableRateLimit": True,
            }

            # NOTE: API 키가 라이브용이므로 sandbox=True 사용하지 않음
            # 데모 모드의 안전장치는 주문 실행 단계에서 소프트웨어로 제어
            if self._settings.is_demo:
                logger.info("🔧 데모 모드 (주문 실행 차단, 시장 데이터만 조회)")
            else:
                logger.warning("⚠️  라이브(Live) 모드 — 실제 주문 실행됨!")

            self._exchange = ccxt.bitget(config)
            await self._exchange.load_markets()
            logger.info("✅ Bitget 연결 성공")

        return self._exchange

    async def close(self):
        """연결 종료"""
        if self._exchange:
            await self._exchange.close()
            self._exchange = None
            logger.info("Bitget 연결 종료")

    # === 계정 관련 ===

    async def get_balance(self) -> Dict[str, Any]:
        """USDT 잔고 조회"""
        exchange = await self._get_exchange()
        try:
            balance = await exchange.fetch_balance({"type": "swap"})
            usdt = balance.get("USDT", {})
            return {
                "total": float(usdt.get("total", 0)),
                "free": float(usdt.get("free", 0)),
                "used": float(usdt.get("used", 0)),
            }
        except Exception as e:
            logger.error(f"잔고 조회 실패: {e}")
            raise

    # === 시장 데이터 ===

    async def get_ohlcv(
        self,
        symbol: str = CCXT_SYMBOL,
        timeframe: str = "4h",
        limit: int = 200,
        since: Optional[int] = None,
    ) -> List[List]:
        """
        OHLCV 캔들 데이터 조회

        Returns:
            [[timestamp, open, high, low, close, volume], ...]
        """
        exchange = await self._get_exchange()
        try:
            ohlcv = await exchange.fetch_ohlcv(
                symbol, timeframe, since=since, limit=limit
            )
            logger.debug(f"OHLCV 조회: {symbol} {timeframe} x{len(ohlcv)}")
            return ohlcv
        except Exception as e:
            logger.error(f"OHLCV 조회 실패: {e}")
            raise

    async def get_ticker(self, symbol: str = CCXT_SYMBOL) -> Dict[str, Any]:
        """현재 시세 조회"""
        exchange = await self._get_exchange()
        try:
            ticker = await exchange.fetch_ticker(symbol)
            return {
                "symbol": ticker["symbol"],
                "last": ticker["last"],
                "bid": ticker["bid"],
                "ask": ticker["ask"],
                "high": ticker["high"],
                "low": ticker["low"],
                "volume": ticker["baseVolume"],
                "timestamp": ticker["timestamp"],
            }
        except Exception as e:
            logger.error(f"시세 조회 실패: {e}")
            raise

    # === 포지션 ===

    async def get_positions(self, symbol: str = CCXT_SYMBOL) -> List[Dict]:
        """현재 포지션 조회"""
        exchange = await self._get_exchange()
        try:
            positions = await exchange.fetch_positions([symbol])
            active = [
                {
                    "symbol": p["symbol"],
                    "side": p["side"],
                    "size": float(p["contracts"] or 0),
                    "entry_price": float(p["entryPrice"] or 0),
                    "unrealized_pnl": float(p["unrealizedPnl"] or 0),
                    "leverage": int(p["leverage"] or 1),
                    "liquidation_price": float(p["liquidationPrice"] or 0),
                    "margin_mode": p.get("marginMode", "isolated"),
                }
                for p in positions
                if float(p.get("contracts") or 0) > 0
            ]
            return active
        except Exception as e:
            logger.error(f"포지션 조회 실패: {e}")
            raise

    async def has_open_position(self, symbol: str = CCXT_SYMBOL) -> bool:
        """포지션 존재 여부"""
        positions = await self.get_positions(symbol)
        return len(positions) > 0

    # === 주문 ===

    async def set_leverage(
        self, leverage: int = DEFAULT_LEVERAGE, symbol: str = CCXT_SYMBOL
    ):
        """레버리지 설정"""
        exchange = await self._get_exchange()
        try:
            await exchange.set_leverage(leverage, symbol)
            logger.info(f"레버리지 설정: {leverage}x")
        except Exception as e:
            logger.warning(f"레버리지 설정 실패 (이미 설정됨일 수 있음): {e}")

    async def set_margin_mode(
        self, mode: str = MARGIN_MODE, symbol: str = CCXT_SYMBOL
    ):
        """마진 모드 설정"""
        exchange = await self._get_exchange()
        try:
            await exchange.set_margin_mode(mode, symbol)
            logger.info(f"마진 모드 설정: {mode}")
        except Exception as e:
            logger.warning(f"마진 모드 설정 실패 (이미 설정됨일 수 있음): {e}")

    async def place_market_order(
        self,
        side: str,
        amount: float,
        symbol: str = CCXT_SYMBOL,
        params: Optional[Dict] = None,
    ) -> Dict:
        """
        시장가 주문

        Args:
            side: 'buy' (롱 진입/숏 청산) 또는 'sell' (숏 진입/롱 청산)
            amount: 수량 (BTC)
            symbol: 심볼
            params: 추가 파라미터 (TP/SL 등)
        """
        # 데모 모드 안전장치
        if self._settings.is_demo:
            ticker = await self.get_ticker(symbol)
            logger.info(f"🔧 [데모] 시장가 주문 시뮬레이션: {side} {amount} @ {ticker['last']}")
            return {
                "id": f"demo_{int(asyncio.get_event_loop().time()*1000)}",
                "symbol": symbol,
                "side": side,
                "amount": amount,
                "price": ticker["last"],
                "status": "closed",
                "demo": True,
            }

        exchange = await self._get_exchange()
        try:
            order = await exchange.create_order(
                symbol=symbol,
                type="market",
                side=side,
                amount=amount,
                params=params or {},
            )
            logger.info(
                f"시장가 주문 체결: {side} {amount} {symbol} @ {order.get('average', 'N/A')}"
            )
            return {
                "id": order["id"],
                "symbol": order["symbol"],
                "side": order["side"],
                "amount": float(order.get("filled", amount)),
                "price": float(order.get("average") or order.get("price") or 0),
                "status": order["status"],
            }
        except Exception as e:
            logger.error(f"주문 실패: {side} {amount} {symbol} - {e}")
            raise

    async def place_limit_order(
        self,
        side: str,
        amount: float,
        price: float,
        symbol: str = CCXT_SYMBOL,
        params: Optional[Dict] = None,
    ) -> Dict:
        """지정가 주문"""
        exchange = await self._get_exchange()
        try:
            order = await exchange.create_order(
                symbol=symbol,
                type="limit",
                side=side,
                amount=amount,
                price=price,
                params=params or {},
            )
            logger.info(f"지정가 주문: {side} {amount} @ {price}")
            return {
                "id": order["id"],
                "symbol": order["symbol"],
                "side": order["side"],
                "amount": float(order.get("amount", amount)),
                "price": price,
                "status": order["status"],
            }
        except Exception as e:
            logger.error(f"지정가 주문 실패: {e}")
            raise

    async def cancel_order(self, order_id: str, symbol: str = CCXT_SYMBOL) -> bool:
        """주문 취소"""
        exchange = await self._get_exchange()
        try:
            await exchange.cancel_order(order_id, symbol)
            logger.info(f"주문 취소: {order_id}")
            return True
        except Exception as e:
            logger.error(f"주문 취소 실패: {order_id} - {e}")
            return False

    async def close_position(
        self, side: str, amount: float, symbol: str = CCXT_SYMBOL
    ) -> Dict:
        """
        포지션 청산 (시장가)

        Args:
            side: 'long' → sell, 'short' → buy
            amount: 청산 수량
        """
        close_side = "sell" if side == "long" else "buy"
        params = {"reduceOnly": True}
        return await self.place_market_order(close_side, amount, symbol, params)
