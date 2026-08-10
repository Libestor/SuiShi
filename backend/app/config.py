from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "岁实 · 投资总览"
    database_url: str = "sqlite:///./investment-overview.db"
    platform_token: str = "dev-investment-token"
    session_secret: str = "dev-session-secret-change-me"
    session_ttl_hours: int = 12
    session_cookie_secure: bool = False
    runner_url: str = "http://runner:9000"
    runner_shared_secret: str = "dev-runner-secret"
    snapshot_interval_minutes: int = 60
    data_source_repo: str = "./data/data-sources"
    scheduler_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
