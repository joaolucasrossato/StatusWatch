from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    worker_max_concurrency: int = Field(default=10, ge=1, le=100)
    worker_poll_interval_seconds: float = Field(default=5, ge=0.1, le=60)
    worker_max_redirects: int = Field(default=5, ge=0, le=10)

    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = ""
    smtp_use_tls: bool = True

    app_name: str = "StatusWatch"
    app_env: str = "development"
    database_url: str
    redis_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    model_config = SettingsConfigDict(
        case_sensitive=False,
    )

settings = Settings()

@lru_cache
def get_settings() -> Settings:
    return Settings()
