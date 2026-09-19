"""Application settings, loaded from the environment (see .env.example)."""

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_SECRET = "dev-only-change-me"


class Settings(BaseSettings):
    # The API usually runs from backend/, but .env lives at the repo root.
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "GymBahi"
    environment: Literal["local", "test", "staging", "production"] = "local"
    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://gymbahi:gymbahi@localhost:5433/gymbahi"

    # --- Sessions (PLAN.md §11) ---
    secret_key: str = INSECURE_SECRET
    access_token_minutes: int = 15
    refresh_token_days: int = 30

    # --- Gyms ---
    trial_days: int = 14

    # How many of OUR proxies sit in front of the API. See client_ip().
    trusted_proxy_count: int = 0

    # --- Files ---
    # Local directory for uploads in development (relative to backend/).
    media_root: str = "media"

    # --- SMS (PLAN.md §15: gateway not chosen yet) ---
    sms_provider: Literal["console", "sparrow", "aakash"] = "console"
    sparrow_token: str | None = None
    # Sparrow's sender identity. Gyms' own sender names need registering with
    # the gateway and operators first (PLAN.md §10).
    sparrow_sender: str = "InfoSMS"
    aakash_token: str | None = None
    # SMS credits a new gym starts its trial with.
    trial_sms_credits: int = 50

    # Where members open their gym's app; goes into SMS links.
    public_app_url: str = "http://localhost:3000"

    # --- Email (sign-in codes by email; they cost nothing, §5.5) ---
    email_provider: Literal["console", "smtp"] = "console"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    email_from: str = "GymBahi <no-reply@gymbahi.com>"

    # --- Member sign-in (§11) ---
    otp_minutes: int = 5
    otp_max_attempts: int = 5
    otp_per_destination: int = 3  # per OTP_WINDOW_MINUTES
    otp_per_ip: int = 20
    otp_window_minutes: int = 15
    member_refresh_days: int = 90
    # Every sign-in code is this, for end-to-end tests only. Refused outside
    # local and test environments, below.
    otp_test_code: str | None = None

    # --- Worker ---
    worker_poll_seconds: float = 5.0

    @model_validator(mode="after")
    def refuse_placeholder_secret(self) -> "Settings":
        if self.environment in ("staging", "production") and (
            self.secret_key == INSECURE_SECRET or len(self.secret_key) < 32
        ):
            raise ValueError("SECRET_KEY must be set to a long random value.")
        if self.otp_test_code and self.environment not in ("local", "test"):
            raise ValueError("OTP_TEST_CODE is for local end-to-end tests only.")
        return self

    @property
    def cookie_secure(self) -> bool:
        """Secure cookies need HTTPS, which local development does not have."""
        return self.environment in ("staging", "production")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
