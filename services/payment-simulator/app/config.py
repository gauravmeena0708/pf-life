from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    service_name: str = "payment-simulator"
    database_url: str = "postgresql+asyncpg://payment_simulator_app:dev@localhost:5432/payment_simulator_db"
    db_pool_size: int = 5
    rabbitmq_url: str = "amqp://epfo:dev@localhost:5672/"
    gateway_jwks_url: str = "http://gateway:8000/internal/jwks"


settings = Settings()
