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

    app_name: str = "GymBhai"
    environment: Literal["local", "test", "staging", "production"] = "local"
    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://gymbhai:gymbhai@localhost:5433/gymbhai"

    # --- Sessions (PLAN.md §11) ---
    secret_key: str = INSECURE_SECRET
    # Two-step sign-in secrets are derived from this (app/core/totp.py). Kept
    # apart from SECRET_KEY so rotating that never breaks people's
    # authenticator apps. Required outside local development and tests.
    totp_key: str | None = None
    access_token_minutes: int = 15
    refresh_token_days: int = 30

    # --- Staff sign-in limits (PLAN.md §16.1) ---
    login_max_failures: int = 5  # per email or phone, per LOGIN_WINDOW_MINUTES
    login_max_failures_per_ip: int = 20
    login_window_minutes: int = 15
    # "Forgot password" codes; asking for them shares the OTP limits below.
    password_reset_minutes: int = 10

    # --- Gyms ---
    trial_days: int = 14

    # How many of OUR proxies sit in front of the API. See client_ip().
    trusted_proxy_count: int = 0

    # --- Files ---
    # "local" keeps uploads on disk (development); "s3" in any S3-compatible
    # bucket, e.g. Cloudflare R2 (production, PLAN.md §3).
    storage_backend: Literal["local", "s3"] = "local"
    # Local directory for uploads in development (relative to backend/).
    media_root: str = "media"
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_region: str = "auto"
    s3_bucket: str | None = None
    # Daily database backups go here (PLAN.md §11), kept BACKUP_KEEP_DAYS.
    backup_bucket: str | None = None
    backup_keep_days: int = 30

    # --- Monitoring ---
    sentry_dsn: str | None = None

    # --- SMS (PLAN.md §15: gateway not chosen yet) ---
    sms_provider: Literal["console", "sparrow", "aakash"] = "console"
    sparrow_token: str | None = None
    # Sparrow's sender identity. Gyms' own sender names need registering with
    # the gateway and operators first (PLAN.md §10).
    sparrow_sender: str = "InfoSMS"
    aakash_token: str | None = None
    # Where gyms pay us (PLAN.md §5.7), shown on their Subscription screen.
    platform_pay_to_name: str | None = None
    platform_pay_to_esewa: str | None = None
    platform_pay_to_bank: str | None = None
    # SMS credits a new gym starts its trial with.
    trial_sms_credits: int = 50

    # Our WhatsApp and Viber number for Help (§16.5, 10.3): country code and
    # number, digits only, e.g. 9779800000000. No number: Help shows the guides.
    support_whatsapp: str | None = None

    # Where members open their gym's app; goes into SMS links.
    public_app_url: str = "http://localhost:3000"

    # --- Email (sign-in codes by email; they cost nothing, §5.5) ---
    email_provider: Literal["console", "smtp"] = "console"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    email_from: str = "GymBhai <no-reply@gymbhai.com>"

    # --- Web Push to the member app (PLAN.md §16.3, 8.3) ---
    # `console` logs what would be sent; `webpush` sends it. Push works only
    # with a key: make one with `python -m scripts.vapid_keys`.
    push_provider: Literal["console", "webpush"] = "console"
    # The VAPID private key: base64url of the raw 32-byte P-256 key.
    vapid_private_key: str | None = None
    # Who push services contact about our messages.
    vapid_subject: str = "mailto:support@gymbhai.com"
    # The phone app's push goes through Expo (§17.6). A token is optional;
    # with "enhanced push security" on in the Expo project, it is required.
    expo_access_token: str | None = None

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
    # While no SMS gateway is set up (PLAN.md §15) sign-in codes only reach the
    # log, so members can sign in with this code instead. Member sign-in only;
    # never staff password resets. Refused once SMS_PROVIDER is a real gateway,
    # so it can't outlive the need for it.
    master_otp: str | None = None

    # --- Worker ---
    worker_poll_seconds: float = 5.0

    @model_validator(mode="after")
    def refuse_placeholder_secret(self) -> "Settings":
        if self.environment in ("staging", "production") and (
            self.secret_key == INSECURE_SECRET or len(self.secret_key) < 32
        ):
            raise ValueError("SECRET_KEY must be set to a long random value.")
        if self.environment in ("staging", "production") and (
            not self.totp_key or len(self.totp_key) < 32
        ):
            raise ValueError("TOTP_KEY must be set to a long random value.")
        if self.environment == "test" and (
            self.email_provider != "console"
            or self.sms_provider != "console"
            or self.push_provider != "console"
        ):
            raise ValueError("Tests never send real email, SMS or push: use console.")
        if self.push_provider == "webpush" and not self.vapid_private_key:
            raise ValueError("PUSH_PROVIDER=webpush needs VAPID_PRIVATE_KEY.")
        if self.master_otp:
            if self.sms_provider != "console":
                raise ValueError(
                    "MASTER_OTP is only for while there is no SMS gateway: remove it."
                )
            code = self.master_otp
            if not (len(code) == 6 and code.isdigit()):
                raise ValueError("MASTER_OTP must be 6 digits.")
            # Locally anything goes; on a server anyone could try 111111.
            if self.environment in ("staging", "production") and (
                len(set(code)) < 3 or code in ("123456", "654321")
            ):
                raise ValueError("MASTER_OTP must be 6 digits that are hard to guess.")
        if self.otp_test_code and self.environment not in ("local", "test"):
            raise ValueError("OTP_TEST_CODE is for local end-to-end tests only.")
        if self.storage_backend == "s3" and not (
            self.s3_bucket and self.s3_access_key_id and self.s3_secret_access_key
        ):
            raise ValueError("STORAGE_BACKEND=s3 needs S3_BUCKET and S3 keys.")
        return self

    @property
    def cookie_secure(self) -> bool:
        """Secure cookies need HTTPS, which local development does not have."""
        return self.environment in ("staging", "production")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
