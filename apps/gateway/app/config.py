from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    redis_url: str = "redis://redis:6379/0"
    # Public issuer: what the browser is redirected to and what tokens carry in `iss`.
    keycloak_issuer: str = "http://localhost:8080/realms/epfo-demo"
    # Back-channel base (token, JWKS) reachable from inside the Docker network; empty = use the issuer host.
    keycloak_internal_url: str = ""
    keycloak_client_id: str = "epfo-bff"
    keycloak_client_secret: str = ""
    gateway_session_fernet_key: str = ""
    gateway_signing_key_pem: str = ""
    session_idle_seconds: int = 1800
    session_max_seconds: int = 28800
    gateway_public_origin: str = "http://localhost:8000"
    device_hash_salt: str = "dev-device-salt"      # salts the device-cookie hash reported in security events


@lru_cache
def get_settings() -> Settings:
    return Settings()
