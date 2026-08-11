from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PUBLIC_DEVELOPMENT_CREDENTIALS = {
    "dev-investment-token",
    "dev-session-secret-change-me",
    "dev-runner-secret",
    "replace-with-a-long-random-session-secret",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "岁实 · 投资总览"
    database_url: str = "sqlite:///./investment-overview.db"
    platform_token: str = Field(min_length=32)
    session_secret: str = Field(min_length=32)
    session_ttl_hours: int = 12
    session_cookie_secure: bool = False
    runner_url: str = "http://runner:9000"
    runner_shared_secret: str = Field(min_length=32)
    trusted_proxy_cidrs: str = ""
    login_rate_limit_max_identities: int = Field(default=10_000, ge=100, le=1_000_000)
    snapshot_interval_minutes: int = 60
    data_source_repo: str = "./data/data-sources"
    scheduler_enabled: bool = False
    # Sample holdings and historical transactions must be an explicit local-demo choice.
    seed_demo_data: bool = False

    @model_validator(mode="after")
    def validate_security_credentials(self) -> "Settings":
        credentials = {
            "PLATFORM_TOKEN": self.platform_token.strip(),
            "SESSION_SECRET": self.session_secret.strip(),
            "RUNNER_SHARED_SECRET": self.runner_shared_secret.strip(),
        }
        for name, value in credentials.items():
            if value in PUBLIC_DEVELOPMENT_CREDENTIALS:
                raise ValueError(f"{name} must not use a public development credential")
        if len(set(credentials.values())) != len(credentials):
            raise ValueError("PLATFORM_TOKEN, SESSION_SECRET, and RUNNER_SHARED_SECRET must differ")
        self.platform_token = credentials["PLATFORM_TOKEN"]
        self.session_secret = credentials["SESSION_SECRET"]
        self.runner_shared_secret = credentials["RUNNER_SHARED_SECRET"]
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
