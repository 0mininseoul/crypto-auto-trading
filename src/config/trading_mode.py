"""
거래 모드 관리 (DB 기반)
데모/라이브 모드를 DB에서 읽고 쓰며, 런타임 전환 지원
"""
from typing import Optional
from src.utils.logger import setup_logger

logger = setup_logger("trading_mode")

# 메모리 캐시 (DB 호출 최소화)
_current_mode: Optional[str] = None
_mode_change_callbacks: list = []


def get_trading_mode() -> str:
    """
    현재 거래 모드 반환 (DB에서 읽음)

    Returns:
        "demo" 또는 "live"
    """
    global _current_mode

    # 캐시된 값이 있으면 반환
    if _current_mode is not None:
        return _current_mode

    # DB에서 읽기
    try:
        from src.database.repository import BotStatusRepository
        status = BotStatusRepository.get_status()
        if status and status.get("trading_mode"):
            _current_mode = status["trading_mode"].lower()
        else:
            # DB에 값이 없으면 기본값 demo
            _current_mode = "demo"
            logger.info("거래 모드 기본값 설정: demo")
    except Exception as e:
        logger.warning(f"DB에서 거래 모드 읽기 실패, 기본값 사용: {e}")
        _current_mode = "demo"

    return _current_mode


def set_trading_mode(mode: str) -> bool:
    """
    거래 모드 변경 (DB 저장 + 콜백 실행)

    Args:
        mode: "demo" 또는 "live"

    Returns:
        성공 여부
    """
    global _current_mode

    mode = mode.lower()
    if mode not in ["demo", "live"]:
        logger.error(f"유효하지 않은 거래 모드: {mode}")
        return False

    old_mode = _current_mode

    # DB에 저장
    try:
        from src.database.repository import BotStatusRepository
        BotStatusRepository.update_status(trading_mode=mode)
        _current_mode = mode
        logger.info(f"거래 모드 변경: {old_mode} → {mode}")

        # 모드 변경 콜백 실행
        for callback in _mode_change_callbacks:
            try:
                callback(mode)
            except Exception as e:
                logger.error(f"모드 변경 콜백 실행 실패: {e}")

        return True
    except Exception as e:
        logger.error(f"거래 모드 변경 실패: {e}")
        return False


def is_demo_mode() -> bool:
    """데모 모드인지 확인"""
    return get_trading_mode() == "demo"


def is_live_mode() -> bool:
    """라이브 모드인지 확인"""
    return get_trading_mode() == "live"


def register_mode_change_callback(callback) -> None:
    """
    모드 변경 시 호출될 콜백 등록

    Args:
        callback: mode 인자를 받는 함수
    """
    _mode_change_callbacks.append(callback)


def clear_cache() -> None:
    """모드 캐시 초기화 (테스트용)"""
    global _current_mode
    _current_mode = None
