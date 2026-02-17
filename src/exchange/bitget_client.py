"""
Bitget REST API 클라이언트 (Async ccxt)
잔고 조회, OHLCV, 주문, 포지션 관리
"""
import asyncio
from typing import Optional, List, Dict, Any

import ccxt.async_support as ccxt

from src.config.settings import get_settings
from src.config.trading_mode import is_demo_mode
from src.config.constants import (
    CCXT_SYMBOL, DEMO_CCXT_SYMBOL, MARGIN_MODE, DEFAULT_LEVERAGE
)
from src.utils.logger import setup_logger

logger = setup_logger("bitget_client")


# 싱글톤 인스턴스 (모드 전환 시 재연결을 위해)
_client_instance: Optional["BitgetClient"] = None


def get_bitget_client() -> "BitgetClient":
    """BitgetClient 싱글톤 반환"""
    global _client_instance
    if _client_instance is None:
        _client_instance = BitgetClient()
    return _client_instance


class BitgetClient:
    """Bitget 거래소 비동기 클라이언트"""

    def __init__(self):
        settings = get_settings()
        self._exchange: Optional[ccxt.bitget] = None
        self._settings = settings
        self._current_mode: Optional[str] = None  # 연결 시점의 모드 저장
        self._position_mode: Optional[str] = None  # 'one_way' 또는 'hedge'

    @property
    def symbol(self) -> str:
        """현재 모드에 맞는 심볼 반환"""
        if is_demo_mode():
            return DEMO_CCXT_SYMBOL
        return CCXT_SYMBOL

    async def reconnect(self) -> None:
        """
        거래소 재연결 (모드 전환 시 호출)
        기존 연결을 닫고 새 모드로 재연결
        """
        logger.info("🔄 Bitget 재연결 중...")
        await self.close()
        # 다음 _get_exchange 호출 시 새 모드로 연결됨
        await self._get_exchange()

    async def _get_exchange(self) -> ccxt.bitget:
        """ccxt 거래소 인스턴스 (lazy init)"""
        if self._exchange is None:
            # 현재 모드 확인
            is_demo = is_demo_mode()
            self._current_mode = "demo" if is_demo else "live"

            # 기존 API 키 사용 (데모/라이브 동일)
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

            # 데모 트레이딩 모드 (Bitget paptrading)
            if is_demo:
                # Bitget 데모 모드: 헤더에 paptrading=1 추가
                config["options"]["headers"] = {"PAPTRADING": "1"}
                logger.info(f"🧪 데모 트레이딩 모드 — 심볼: {self.symbol}")
            else:
                logger.warning("⚠️  라이브(Live) 모드 — 실제 주문 실행됨!")

            self._exchange = ccxt.bitget(config)
            await self._exchange.load_markets()

            # 포지션 모드 확인
            await self._detect_position_mode()
            logger.info("✅ Bitget 연결 성공")

        return self._exchange

    async def _detect_position_mode(self) -> str:
        """
        계정의 포지션 모드 확인 (One-way / Hedge)

        Returns:
            'one_way' 또는 'hedge'
        """
        if self._position_mode:
            return self._position_mode

        try:
            # Bitget v2 API로 계정 설정 조회
            response = await self._exchange.privateMixGetV2MixAccountAccount({
                "symbol": self.symbol.replace("/", "").replace(":SUSDT", "").replace(":USDT", ""),
                "productType": "SUSDT-FUTURES" if is_demo_mode() else "USDT-FUTURES",
                "marginCoin": "SUSDT" if is_demo_mode() else "USDT",
            })

            # holdMode: 'single_hold' (one-way) / 'double_hold' (hedge)
            hold_mode = response.get("data", {}).get("holdMode", "single_hold")
            self._position_mode = "one_way" if hold_mode == "single_hold" else "hedge"
            logger.info(f"📋 포지션 모드: {self._position_mode} ({hold_mode})")

            # ccxt에 포지션 모드 설정 (one-way = False, hedge = True)
            if self._position_mode == "one_way":
                try:
                    await self._exchange.set_position_mode(False, self.symbol)
                    logger.info("📋 ccxt 포지션 모드 설정: one-way")
                except Exception as mode_err:
                    logger.debug(f"ccxt 포지션 모드 설정 스킵 (이미 설정됨): {mode_err}")

        except Exception as e:
            # 조회 실패 시 기본값 one_way (Bitget 기본값)
            logger.warning(f"포지션 모드 조회 실패, 기본값(one_way) 사용: {e}")
            self._position_mode = "one_way"

        return self._position_mode

    async def close(self):
        """연결 종료"""
        if self._exchange:
            await self._exchange.close()
            self._exchange = None
            logger.info("Bitget 연결 종료")

    # === 계정 관련 ===

    async def get_balance(self) -> Dict[str, Any]:
        """USDT (또는 SUSDT) 잔고 조회"""
        exchange = await self._get_exchange()
        is_demo = is_demo_mode()
        
        # 데모 모드: SUSDT-FUTURES, 라이브: USDT-FUTURES
        params = {"type": "swap"}
        if is_demo:
            params["productType"] = "SUSDT-FUTURES"
        
        try:
            balance = await exchange.fetch_balance(params)
            
            # 데모면 SUSDT, 아니면 USDT 확인
            currency = "SUSDT" if is_demo else "USDT"
            target_balance = balance.get(currency, {})

            return {
                "total": float(target_balance.get("total", 0)),
                "free": float(target_balance.get("free", 0)),
                "used": float(target_balance.get("used", 0)),
            }
        except Exception as e:
            logger.error(f"잔고 조회 실패: {e}")
            raise

    # === 시장 데이터 ===

    async def get_ohlcv(
        self,
        symbol: Optional[str] = None,
        timeframe: str = "4h",
        limit: int = 200,
        since: Optional[int] = None,
    ) -> List[List]:
        """
        OHLCV 캔들 데이터 조회

        Returns:
            [[timestamp, open, high, low, close, volume], ...]
        """
        if symbol is None:
            symbol = self.symbol
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

    async def get_ticker(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """현재 시세 조회"""
        if symbol is None:
            symbol = self.symbol
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

    async def get_positions(self, symbol: Optional[str] = None) -> List[Dict]:
        """현재 포지션 조회"""
        if symbol is None:
            symbol = self.symbol
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

    async def has_open_position(self, symbol: Optional[str] = None) -> bool:
        """포지션 존재 여부"""
        if symbol is None:
            symbol = self.symbol
        positions = await self.get_positions(symbol)
        return len(positions) > 0

    # === 주문 ===

    async def set_leverage(
        self, leverage: int = DEFAULT_LEVERAGE, symbol: Optional[str] = None
    ):
        """레버리지 설정"""
        if symbol is None:
            symbol = self.symbol
        exchange = await self._get_exchange()
        try:
            await exchange.set_leverage(leverage, symbol)
            logger.info(f"레버리지 설정: {leverage}x")
        except Exception as e:
            logger.warning(f"레버리지 설정 실패 (이미 설정됨일 수 있음): {e}")

    async def set_margin_mode(
        self, mode: str = MARGIN_MODE, symbol: Optional[str] = None
    ):
        """마진 모드 설정"""
        if symbol is None:
            symbol = self.symbol
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
        symbol: Optional[str] = None,
        params: Optional[Dict] = None,
        position_side: Optional[str] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Dict:
        """
        시장가 주문

        Args:
            side: 'buy' (롱 진입/숏 청산) 또는 'sell' (숏 진입/롱 청산)
            amount: 수량 (BTC)
            symbol: 심볼 (기본값: 현재 모드에 맞는 심볼)
            params: 추가 파라미터 (TP/SL 등)
            position_side: 'long', 'short' (Hedge 모드용) 또는 None (One-way 모드)
            stop_loss: 손절가 (거래소에 설정)
            take_profit: 익절가 (거래소에 설정)
        """
        # 심볼 기본값 설정
        if symbol is None:
            symbol = self.symbol

        exchange = await self._get_exchange()

        # 파라미터 병합
        order_params = params.copy() if params else {}

        # TP/SL 설정 (Bitget presetStopLossPrice / presetTakeProfitPrice)
        # Bitget은 가격이 0.1의 배수여야 함 (오류 코드 45115)
        if stop_loss and not order_params.get("reduceOnly", False):
            stop_loss = round(stop_loss, 1)
            order_params["presetStopLossPrice"] = str(stop_loss)
            logger.info(f"📍 손절가 설정: ${stop_loss:,.1f}")
        if take_profit and not order_params.get("reduceOnly", False):
            take_profit = round(take_profit, 1)
            order_params["presetTakeProfitPrice"] = str(take_profit)
            logger.info(f"📍 익절가 설정: ${take_profit:,.1f}")

        # 포지션 모드에 따른 파라미터 설정
        if self._position_mode == "one_way":
            # One-way 모드: tradeSide 파라미터로 진입/청산 구분
            is_reduce = order_params.get("reduceOnly", False)
            order_params["tradeSide"] = "close" if is_reduce else "open"
            order_params["oneWayMode"] = True
            order_params.pop("posSide", None)
            order_params.pop("holdSide", None)
            logger.debug(f"One-way 모드 주문: {side} tradeSide={order_params['tradeSide']}")
        else:
            # Hedge 모드: posSide 필수
            if position_side:
                order_params["posSide"] = position_side
            elif "reduceOnly" in order_params and order_params["reduceOnly"]:
                # 청산 시 반대 포지션
                order_params["posSide"] = "short" if side == "buy" else "long"
            else:
                # 신규 진입 시
                order_params["posSide"] = "long" if side == "buy" else "short"
            logger.debug(f"Hedge 모드 주문: {side} posSide={order_params.get('posSide')}")

        try:
            order = await exchange.create_order(
                symbol=symbol,
                type="market",
                side=side,
                amount=amount,
                params=order_params,
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
        symbol: Optional[str] = None,
        params: Optional[Dict] = None,
    ) -> Dict:
        """지정가 주문"""
        if symbol is None:
            symbol = self.symbol
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

    async def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> bool:
        """주문 취소"""
        if symbol is None:
            symbol = self.symbol
        exchange = await self._get_exchange()
        try:
            await exchange.cancel_order(order_id, symbol)
            logger.info(f"주문 취소: {order_id}")
            return True
        except Exception as e:
            logger.error(f"주문 취소 실패: {order_id} - {e}")
            return False

    async def close_position(
        self, side: str, amount: float, symbol: Optional[str] = None
    ) -> Dict:
        """
        포지션 청산 (시장가)

        Args:
            side: 'long' → sell, 'short' → buy
            amount: 청산 수량
        """
        if symbol is None:
            symbol = self.symbol
        close_side = "sell" if side == "long" else "buy"
        params = {"reduceOnly": True}
        return await self.place_market_order(close_side, amount, symbol, params)
