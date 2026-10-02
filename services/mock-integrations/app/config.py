from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    service_name: str = "mock-integrations"
    database_url: str = "postgresql+asyncpg://mock_integrations_app:dev@localhost:5432/mock_integrations_db"
    db_pool_size: int = 5
    rabbitmq_url: str = "amqp://epfo:dev@localhost:5672/"
    gateway_jwks_url: str = "http://gateway:8000/internal/jwks"
    mock_trust_api_secret: str = "change-me-trust-api-secret"
    mock_gateway_secret: str = "change-me-mock-gateway-secret"


settings = Settings()
