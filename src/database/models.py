"""
Pydantic 데이터 모델
"""
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum

from src.utils.helpers import kst_now


class TradeSide(str, Enum):
    LONG = "long"
    SHORT = "short"


class TradeStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class BotState(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class TradingMode(str, Enum):
    DEMO = "demo"
    LIVE = "live"


class Trade(BaseModel):
    """거래 기록"""
    id: Optional[int] = None
    symbol: str = "BTCUSDT"
    side: TradeSide
    entry_price: float
    exit_price: Optional[float] = None
    quantity: float
    leverage: int
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    status: TradeStatus = TradeStatus.OPEN
    entry_reason: Optional[Dict[str, Any]] = None
    exit_reason: Optional[str] = None
    tp_levels_executed: Optional[List[int]] = None  # 실행된 TP 레벨 목록 (중복 실행 방지)
    entry_time: datetime = Field(default_factory=kst_now)
    exit_time: Optional[datetime] = None
    created_at: Optional[datetime] = None


class DailyPerformance(BaseModel):
    """일별 성과"""
    id: Optional[int] = None
    date: date
    starting_balance: Optional[float] = None
    ending_balance: Optional[float] = None
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: Optional[float] = None
    max_drawdown: Optional[float] = None
    created_at: Optional[datetime] = None


class BotStatus(BaseModel):
    """봇 상태"""
    id: Optional[int] = None
    status: BotState = BotState.STOPPED
    trading_mode: TradingMode = TradingMode.DEMO
    last_heartbeat: Optional[datetime] = None
    current_position: Optional[Dict[str, Any]] = None
    updated_at: Optional[datetime] = None


class SystemLog(BaseModel):
    """시스템 로그"""
    id: Optional[int] = None
    level: str
    message: str
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None


class TickerData(BaseModel):
    """실시간 시세 데이터"""
    symbol: str
    last_price: float
    bid_price: float
    ask_price: float
    high_24h: float
    low_24h: float
    volume_24h: float
    timestamp: datetime


class CandleData(BaseModel):
    """캔들 데이터"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
