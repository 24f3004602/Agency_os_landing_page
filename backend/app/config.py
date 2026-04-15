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
    secret_key: str
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # SuperAdmin — never in DB
    superadmin_email: str
    superadmin_password: str

    # Database
    database_url: str

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333

    # Embeddings — provider decided at Module 3
    embed_model: str = "tbd"

    # Anthropic
    anthropic_api_key: str = ""

    # Gmail
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_redirect_uri: str = ""

    # WATI
    wati_api_key: str = ""
    wati_base_url: str = ""

    # HubSpot
    hubspot_access_token: str = ""

    # Slack
    slack_bot_token: str = ""
    slack_default_channel: str = "#agency-os-alerts"

    # n8n
    n8n_base_url: str = ""
    n8n_webhook_secret: str = ""

    # CORS
    allowed_origins: str = "http://localhost:5173"
    
    # SerpAPI (M6 — competitor research)
    serpapi_key: str = ""
    
    # Buffer (M5 — social scheduling)
    buffer_access_token: str = ""
    buffer_default_profile_id: str = "" 

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"
    



@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
