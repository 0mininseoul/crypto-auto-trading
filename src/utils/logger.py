"""
구조화 로깅 시스템
콘솔 출력 + Supabase system_logs 테이블 기록
"""
import logging
import sys
from datetime import datetime, timezone
from typing import Optional

from src.config.settings import get_settings


class SupabaseLogHandler(logging.Handler):
    """Supabase system_logs 테이블에 로그를 기록하는 핸들러"""

    def __init__(self):
        super().__init__()
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from src.database.supabase_client import get_supabase_client
                self._client = get_supabase_client()
            except Exception:
                self._client = None
        return self._client

    def emit(self, record: logging.LogRecord):
        if record.levelno < logging.INFO:
            return  # DEBUG는 DB에 저장하지 않음

        client = self._get_client()
        if client is None:
            return

        try:
            log_entry = {
                "level": record.levelname,
                "message": self.format(record),
                "metadata": {
                    "module": record.module,
                    "funcName": record.funcName,
                    "lineno": record.lineno,
                },
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            client.table("system_logs").insert(log_entry).execute()
        except Exception:
            pass  # DB 로깅 실패 시 무시 (무한 루프 방지)


def setup_logger(name: str = "trading_bot") -> logging.Logger:
    """
    로거 초기화

    Args:
        name: 로거 이름

    Returns:
        설정된 Logger 인스턴스
    """
    settings = get_settings()
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # 이미 설정됨

    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logger.setLevel(log_level)

    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_format = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s | %(name)s.%(funcName)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # Supabase 핸들러 (INFO 이상만)
    try:
        supabase_handler = SupabaseLogHandler()
        supabase_handler.setLevel(logging.INFO)
        supabase_format = logging.Formatter("%(message)s")
        supabase_handler.setFormatter(supabase_format)
        logger.addHandler(supabase_handler)
    except Exception:
        logger.warning("Supabase log handler 초기화 실패 - 콘솔만 사용")

    return logger


# 기본 로거
logger = setup_logger()
