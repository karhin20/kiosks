from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralized runtime configuration loaded from environment variables.
    """

    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_ANON_KEY: str | None = None
    SUPABASE_STORAGE_BUCKET: str = "product-images"
    MESSENGER_URL: str = "http://localhost:4000/notify"
    MESSENGER_SECRET: str = "PLACEHOLDER_SECRET_CHANGE_ME" # Set this in your .env file
    API_PREFIX: str = "/api"
    APP_NAME: str = "Lampo API"
    ALLOWED_ORIGINS: list[str] = ["http://localhost:8080"]  # Safe defaults, override in .env for production
    OAUTH_REDIRECT_URL: str = "http://localhost:8080/auth/callback"  # Override in .env for production

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # If ALLOWED_ORIGINS is a string, it might be a JSON list or comma-separated
    if isinstance(settings.ALLOWED_ORIGINS, str):
        import json
        raw = settings.ALLOWED_ORIGINS.strip()
        if raw.startswith("[") and raw.endsWith("]"):
            try:
                settings.ALLOWED_ORIGINS = json.loads(raw)
            except Exception:
                settings.ALLOWED_ORIGINS = [s.strip() for s in raw[1:-1].split(",") if s.strip()]
        else:
            settings.ALLOWED_ORIGINS = [s.strip() for s in raw.split(",") if s.strip()]
    
    # Ensure all origins are strings and stripped
    if isinstance(settings.ALLOWED_ORIGINS, list):
        settings.ALLOWED_ORIGINS = [str(o).strip() for o in settings.ALLOWED_ORIGINS if o]
        
    return settings

