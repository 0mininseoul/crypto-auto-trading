"""
Supabase 클라이언트 싱글톤
"""
from typing import Optional
from supabase import create_client, Client

from src.config.settings import get_settings

_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """Supabase 클라이언트 싱글톤 반환"""
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.supabase_url or not settings.supabase_key:
            raise ValueError("SUPABASE_URL과 SUPABASE_KEY가 설정되지 않았습니다.")
        _client = create_client(settings.supabase_url, settings.supabase_key)
    return _client
