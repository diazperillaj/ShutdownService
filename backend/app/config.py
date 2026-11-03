from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración leída de variables de entorno (o de un archivo .env)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    agent_token: SecretStr
    # URL pública exacta del panel; se compara con la cabecera Origin.
    public_origin: str

    session_ttl_hours: int = 168
    cookie_secure: bool = True
    enable_docs: bool = False

    # Tiempo máximo que se espera la confirmación del agente.
    ack_timeout_seconds: float = 3.0

    login_max_attempts: int = 5
    login_lockout_minutes: int = 15
    login_ip_attempts_per_minute: int = 10

    alexa_skill_id: str = ""
    alexa_allowed_user_id: str = ""

    @field_validator("agent_token")
    @classmethod
    def _agent_token_length(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("AGENT_TOKEN debe tener al menos 32 caracteres")
        return value

    @field_validator("public_origin")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")
