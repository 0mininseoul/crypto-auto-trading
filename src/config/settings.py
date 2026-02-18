"""
환경변수 설정 관리
Pydantic BaseSettings를 사용한 타입 안전한 설정
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """전체 앱 설정"""

    # --- Bitget API ---
    # 동일한 API 키로 데모/라이브 모두 사용 (헤더로 구분)
    bitget_api_key: str = Field(default="", alias="BITGET_API_KEY")
    bitget_secret_key: str = Field(default="", alias="BITGET_SECRET_KEY")
    bitget_passphrase: str = Field(default="", alias="BITGET_PASSPHRASE")

    # --- Trading ---
    trading_bot_enabled: bool = Field(default=True, alias="TRADING_BOT_ENABLED")

    # --- Discord ---
    discord_bot_token: str = Field(default="", alias="DISCORD_BOT_TOKEN")
    discord_guild_id: str = Field(default="", alias="DISCORD_GUILD_ID")
    discord_channel_id: str = Field(default="", alias="DISCORD_CHANNEL_ID")
    discord_admin_id: str = Field(default="", alias="DISCORD_ADMIN_ID")

    # --- Supabase ---
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_key: str = Field(default="", alias="SUPABASE_KEY")

    # --- Gemini AI ---
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")

    # --- Logging ---
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# 싱글톤 인스턴스
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """설정 싱글톤 반환"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
