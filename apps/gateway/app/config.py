from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    redis_url: str = "redis://redis:6379/0"
    keycloak_issuer: str = "http://keycloak:8080/realms/epfo-demo"
    keycloak_client_id: str = "epfo-bff"
    keycloak_client_secret: str = ""
    gateway_session_fernet_key: str = ""
    gateway_signing_key_pem: str = ""
    session_idle_seconds: int = 1800
    session_max_seconds: int = 28800
    gateway_public_origin: str = "http://localhost:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
