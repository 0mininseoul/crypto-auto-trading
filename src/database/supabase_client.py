"""
Supabase 클라이언트 싱글톤
"""
from typing import Optional, Any

from src.config.settings import get_settings

_client: Optional[Any] = None


def get_supabase_client() -> Any:
    """Supabase 클라이언트 싱글톤 반환"""
    global _client
    if _client is None:
        # 테스트 환경에서 supabase 의존성(binary 포함) 로딩으로 인한 ImportError를
        # 줄이기 위해 지연 import를 사용한다.
        from supabase import create_client

        settings = get_settings()
        if not settings.supabase_url or not settings.supabase_key:
            raise ValueError("SUPABASE_URL과 SUPABASE_KEY가 설정되지 않았습니다.")
        _client = create_client(settings.supabase_url, settings.supabase_key)
    return _client
