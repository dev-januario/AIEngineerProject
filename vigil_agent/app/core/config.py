from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # App
    app_env: str = "development"
    debug: bool = True
    log_level: str = "INFO"

    # Database
    database_url: str = "mysql+aiomysql://vigil:vigil123@localhost:3306/vigildb"

    # Anthropic
    anthropic_api_key: str = ""

    # Security
    secret_key: str = "change-me-in-production"
    api_key: str = "vigil-internal-api-key-2024"

    # Twilio (WhatsApp)
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"

    # SendGrid (Email)
    sendgrid_api_key: str = ""
    email_from: str = "noreply@vigil.ai"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
