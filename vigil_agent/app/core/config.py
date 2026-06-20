from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

# Resolve o .env na raiz do projeto (AIEngineerProject/), independente
# de onde o uvicorn é iniciado (vigil_agent/ ou raiz).
# Testamos múltiplos caminhos possíveis para garantir que o .env seja encontrado.
_HERE = Path(__file__).resolve().parent          # app/core/
_ENV_CANDIDATES = [
    _HERE.parent.parent.parent / ".env",         # AIEngineerProject/.env  (normal)
    _HERE.parent.parent.parent.parent / ".env",  # um nível acima (fallback)
    Path.cwd() / ".env",                         # diretório atual
    Path.cwd().parent / ".env",                  # pai do diretório atual
]
_ENV_FILE = next((p for p in _ENV_CANDIDATES if p.exists()), _HERE.parent.parent.parent / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_ignore_empty=True,   # variáveis de ambiente vazias NÃO sobrescrevem o .env
        extra="ignore",          # ignora variáveis desconhecidas
    )

    # App
    app_env: str = "development"
    debug: bool = True
    log_level: str = "INFO"

    # Database
    database_url: str = "mysql+aiomysql://vigil:vigil123@localhost:3306/vigildb"

    # Gemini
    gemini_api_key: str = ""  # lido como API_KEY_AI no .env
    api_key_ai: str = ""  # alias direto da env var

    @property
    def _gemini_key(self) -> str:
        """Retorna a chave Gemini, priorizando api_key_ai (API_KEY_AI no .env)."""
        return self.api_key_ai or self.gemini_api_key

    # Security
    secret_key: str = "change-me-in-production"
    vigil_api_key: str = "vigil-internal-api-key-2026"

    # Twilio (WhatsApp)
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"

    # SMTP (Email — Gmail App Password recomendado)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""  # Gmail App Password
    email_from: str = "noreply@vigil.ai"
    email_from_name: str = "Vigil Summit"

    # IMAP (polling de replies — usa mesmas credenciais do SMTP Gmail)
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_poll_interval_seconds: int = 60  # verifica a cada 60s

    # Apollo.io (enriquecimento de perfil por LinkedIn URL ou email)
    apollo_api_key: str = ""  # https://app.apollo.io → Settings → Integrations → API

    # Admin Panel JWT
    admin_jwt_secret: str = "vigil-admin-secret-change-in-production"
    admin_jwt_expire_minutes: int = 5
    admin_default_user: str = "admin"
    admin_default_password: str = "vigil2026"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
