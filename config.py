import os
from dataclasses import dataclass


def _normalize_database_url(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "NICALIA POS SUITE")
    app_env: str = os.getenv("APP_ENV", "development").strip().lower()

    database_url: str = _normalize_database_url(
        os.getenv("DATABASE_URL", "sqlite:///./local.db")
    )

    admin_pin: str = os.getenv("ADMIN_PIN", "1234").strip()
    admin_api_token: str = os.getenv("ADMIN_API_TOKEN", "1234").strip()

    secret_key: str = os.getenv("SECRET_KEY", "nicalia-dev-secret-key").strip()

    session_warning_seconds: int = int(os.getenv("SESSION_WARNING_SECONDS", "60"))
    default_idle_timeout_seconds: int = int(
        os.getenv("DEFAULT_IDLE_TIMEOUT_SECONDS", "300")
    )

    owner_role_code: str = "owner"
    admin_role_code: str = "admin"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()
