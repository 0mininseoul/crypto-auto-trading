"""
DB 연결 장애 시 로컬 큐잉 시스템
연결 복구 시 대기 중인 작업 일괄 처리
"""
import json
import asyncio
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from threading import Lock

from src.utils.logger import setup_logger

logger = setup_logger("db_queue")

# 로컬 큐 저장 경로
QUEUE_FILE = Path("/tmp/btc_bot_db_queue.json")
MAX_QUEUE_SIZE = 1000  # 최대 큐 크기


class DBOperationQueue:
    """
    DB 작업 로컬 큐

    Supabase 연결 실패 시 작업을 임시 저장하고,
    연결 복구 시 일괄 재시도합니다.
    """

    _instance: Optional["DBOperationQueue"] = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._queue: deque = deque(maxlen=MAX_QUEUE_SIZE)
        self._is_connected = True
        self._retry_handlers: Dict[str, Callable] = {}
        self._initialized = True
        self._load_from_file()

    def register_retry_handler(self, operation_type: str, handler: Callable):
        """재시도 핸들러 등록"""
        self._retry_handlers[operation_type] = handler

    def enqueue(self, operation_type: str, data: Dict[str, Any]):
        """
        작업을 큐에 추가

        Args:
            operation_type: 작업 유형 (예: "save_trade", "update_trade", "save_log")
            data: 작업 데이터
        """
        operation = {
            "type": operation_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
            "retry_count": 0,
        }
        self._queue.append(operation)
        self._save_to_file()
        logger.warning(
            f"📥 DB 작업 큐잉: {operation_type} (큐 크기: {len(self._queue)})"
        )

    def set_connection_status(self, is_connected: bool):
        """연결 상태 업데이트"""
        was_disconnected = not self._is_connected
        self._is_connected = is_connected

        if is_connected and was_disconnected and len(self._queue) > 0:
            logger.info(f"🔄 DB 연결 복구 — 대기 작업 {len(self._queue)}개 재시도")

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    def get_pending_operations(self) -> List[Dict]:
        """대기 중인 작업 목록 반환"""
        return list(self._queue)

    def clear_completed(self, count: int):
        """완료된 작업 제거"""
        for _ in range(min(count, len(self._queue))):
            self._queue.popleft()
        self._save_to_file()

    async def process_queue(self) -> int:
        """
        큐에 있는 작업 일괄 처리 (비동기)

        Returns:
            성공적으로 처리된 작업 수
        """
        if not self._is_connected or len(self._queue) == 0:
            return 0

        processed = 0
        failed_operations = []

        while self._queue:
            operation = self._queue[0]
            op_type = operation["type"]
            op_data = operation["data"]

            handler = self._retry_handlers.get(op_type)
            if not handler:
                logger.warning(f"⚠️ 핸들러 없음: {op_type}")
                self._queue.popleft()
                continue

            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(op_data)
                else:
                    handler(op_data)

                self._queue.popleft()
                processed += 1
                logger.info(f"✅ 큐 작업 처리 완료: {op_type}")

            except Exception as e:
                operation["retry_count"] += 1
                if operation["retry_count"] >= 3:
                    logger.error(f"❌ 큐 작업 실패 (3회 재시도 초과): {op_type} - {e}")
                    self._queue.popleft()  # 포기
                else:
                    failed_operations.append(self._queue.popleft())
                    logger.warning(
                        f"⚠️ 큐 작업 재시도 예정: {op_type} "
                        f"(시도 {operation['retry_count']}/3)"
                    )
                break  # 실패 시 나머지는 다음 사이클에

        # 실패한 작업 다시 큐에 추가
        for op in failed_operations:
            self._queue.append(op)

        self._save_to_file()
        return processed

    def _save_to_file(self):
        """큐를 파일에 저장 (영속성)"""
        try:
            data = [
                {
                    "type": op["type"],
                    "data": self._serialize_data(op["data"]),
                    "timestamp": op["timestamp"],
                    "retry_count": op["retry_count"],
                }
                for op in self._queue
            ]
            QUEUE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.error(f"큐 파일 저장 실패: {e}")

    def _load_from_file(self):
        """파일에서 큐 로드"""
        try:
            if QUEUE_FILE.exists():
                data = json.loads(QUEUE_FILE.read_text())
                for op in data:
                    self._queue.append(op)
                if len(self._queue) > 0:
                    logger.info(f"📂 큐 파일에서 {len(self._queue)}개 작업 복원")
        except Exception as e:
            logger.error(f"큐 파일 로드 실패: {e}")

    @staticmethod
    def _serialize_data(data: Dict) -> Dict:
        """datetime 등 JSON 직렬화 불가 타입 변환"""
        result = {}
        for key, value in data.items():
            if isinstance(value, datetime):
                result[key] = value.isoformat()
            elif hasattr(value, "value"):  # Enum
                result[key] = value.value
            elif hasattr(value, "model_dump"):  # Pydantic
                result[key] = value.model_dump()
            else:
                result[key] = value
        return result


# 싱글톤 인스턴스
db_queue = DBOperationQueue()
