"""
데이터베이스 CRUD 작업
DB 연결 실패 시 로컬 큐잉 지원
"""
from datetime import datetime, date, timezone
from typing import List, Optional, Dict, Any

from src.database.supabase_client import get_supabase_client
from src.database.models import (
    Trade, TradeStatus, BotStatus, BotState,
    TradingMode, DailyPerformance
)
from src.utils.helpers import kst_now
from src.utils.logger import setup_logger
from src.utils.db_queue import db_queue

logger = setup_logger("repository")


class TradeRepository:
    """거래 기록 CRUD"""

    @staticmethod
    def save_trade(trade: Trade) -> Trade:
        """거래 기록 저장 (DB 실패 시 큐잉)"""
        data = trade.model_dump(exclude={"id", "created_at"}, exclude_none=True)
        # datetime → ISO string
        for key in ["entry_time", "exit_time"]:
            if key in data and isinstance(data[key], datetime):
                data[key] = data[key].isoformat()
        # Enum → string
        if "side" in data and hasattr(data["side"], "value"):
            data["side"] = data["side"].value
        if "status" in data and hasattr(data["status"], "value"):
            data["status"] = data["status"].value

        try:
            client = get_supabase_client()
            result = client.table("trades").insert(data).execute()
            if result.data:
                trade.id = result.data[0]["id"]
                logger.info(f"거래 기록 저장: #{trade.id} {trade.side.value} {trade.symbol}")
                db_queue.set_connection_status(True)
            return trade
        except Exception as e:
            logger.error(f"거래 기록 저장 실패 (큐잉): {e}")
            db_queue.set_connection_status(False)
            db_queue.enqueue("save_trade", data)
            # 임시 ID 할당 (메모리 내)
            trade.id = -1
            return trade

    @staticmethod
    def update_trade(trade_id: int, updates: Dict[str, Any]) -> bool:
        """거래 기록 업데이트 (DB 실패 시 큐잉)"""
        for key in ["entry_time", "exit_time"]:
            if key in updates and isinstance(updates[key], datetime):
                updates[key] = updates[key].isoformat()
        # Enum → string
        if "status" in updates and hasattr(updates["status"], "value"):
            updates["status"] = updates["status"].value

        try:
            client = get_supabase_client()
            result = client.table("trades").update(updates).eq("id", trade_id).execute()
            db_queue.set_connection_status(True)
            return len(result.data) > 0
        except Exception as e:
            logger.error(f"거래 기록 업데이트 실패 (큐잉): {e}")
            db_queue.set_connection_status(False)
            db_queue.enqueue("update_trade", {"trade_id": trade_id, "updates": updates})
            return False

    @staticmethod
    def get_open_trades() -> List[Dict]:
        """열려있는 거래 조회"""
        client = get_supabase_client()
        result = (
            client.table("trades")
            .select("*")
            .eq("status", TradeStatus.OPEN.value)
            .execute()
        )
        return result.data

    @staticmethod
    def get_trades(limit: int = 50, offset: int = 0) -> List[Dict]:
        """거래 내역 조회"""
        client = get_supabase_client()
        result = (
            client.table("trades")
            .select("*")
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return result.data

    @staticmethod
    def get_today_trades() -> List[Dict]:
        """오늘 거래 내역 조회"""
        today = kst_now().date().isoformat()
        client = get_supabase_client()
        result = (
            client.table("trades")
            .select("*")
            .gte("entry_time", f"{today}T00:00:00Z")
            .execute()
        )
        return result.data

    @staticmethod
    def get_today_trade_count() -> int:
        """오늘 거래 횟수"""
        trades = TradeRepository.get_today_trades()
        return len(trades)

    @staticmethod
    def get_today_pnl() -> float:
        """오늘 총 PnL"""
        trades = TradeRepository.get_today_trades()
        return sum(
            float(t.get("pnl", 0) or 0)
            for t in trades
            if t.get("status") == TradeStatus.CLOSED.value
        )


class BotStatusRepository:
    """봇 상태 CRUD"""

    @staticmethod
    def get_status() -> Optional[Dict]:
        """현재 봇 상태 조회"""
        client = get_supabase_client()
        result = (
            client.table("bot_status")
            .select("*")
            .order("id", desc=True)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    @staticmethod
    def update_status(
        status: Optional[BotState] = None,
        trading_mode: Optional[TradingMode | str] = None,
        current_position: Optional[Dict] = None,
    ) -> bool:
        """봇 상태 업데이트"""
        client = get_supabase_client()
        current = BotStatusRepository.get_status()
        if not current:
            return False

        updates: Dict[str, Any] = {
            "updated_at": kst_now().isoformat(),
        }
        if status:
            updates["status"] = status.value if hasattr(status, 'value') else status
        if trading_mode:
            updates["trading_mode"] = trading_mode.value if hasattr(trading_mode, 'value') else trading_mode
        if current_position is not None:
            updates["current_position"] = current_position

        result = (
            client.table("bot_status")
            .update(updates)
            .eq("id", current["id"])
            .execute()
        )
        return len(result.data) > 0

    @staticmethod
    def heartbeat() -> bool:
        """하트비트 업데이트"""
        client = get_supabase_client()
        current = BotStatusRepository.get_status()
        if not current:
            return False
        result = (
            client.table("bot_status")
            .update({
                "last_heartbeat": kst_now().isoformat(),
                "updated_at": kst_now().isoformat(),
            })
            .eq("id", current["id"])
            .execute()
        )
        return len(result.data) > 0

    @staticmethod
    def update_position(position: Optional[Dict] = None) -> bool:
        """현재 포지션 정보 업데이트"""
        return BotStatusRepository.update_status(current_position=position)


class PerformanceRepository:
    """일별 성과 CRUD"""

    @staticmethod
    def save_daily(perf: DailyPerformance) -> DailyPerformance:
        """일별 성과 저장/업데이트"""
        client = get_supabase_client()
        data = perf.model_dump(exclude={"id", "created_at"}, exclude_none=True)
        if "date" in data and isinstance(data["date"], date):
            data["date"] = data["date"].isoformat()
        result = (
            client.table("daily_performance")
            .upsert(data, on_conflict="date")
            .execute()
        )
        if result.data:
            perf.id = result.data[0]["id"]
        return perf

    @staticmethod
    def get_recent(days: int = 30) -> List[Dict]:
        """최근 N일 성과 조회"""
        client = get_supabase_client()
        result = (
            client.table("daily_performance")
            .select("*")
            .order("date", desc=True)
            .limit(days)
            .execute()
        )
        return result.data


class SettingsRepository:
    """설정 CRUD"""

    @staticmethod
    def get(key: str) -> Optional[Any]:
        """설정값 조회"""
        client = get_supabase_client()
        result = (
            client.table("settings")
            .select("value")
            .eq("key", key)
            .execute()
        )
        if result.data:
            return result.data[0]["value"]
        return None

    @staticmethod
    def set(key: str, value: Any) -> bool:
        """설정값 저장/업데이트"""
        client = get_supabase_client()
        data = {
            "key": key,
            "value": value,
            "updated_at": kst_now().isoformat(),
        }
        result = (
            client.table("settings")
            .upsert(data, on_conflict="key")
            .execute()
        )
        return len(result.data) > 0

    @staticmethod
    def get_all() -> Dict[str, Any]:
        """모든 설정 조회"""
        client = get_supabase_client()
        result = client.table("settings").select("key, value").execute()
        return {row["key"]: row["value"] for row in result.data}
