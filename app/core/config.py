"""Application configuration via pydantic-settings."""
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """App settings loaded from environment variables."""
    
    ENVIRONMENT: str = "development"
    DATABASE_URL: str
    REDIS_URL: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    API_TITLE: str = "Cards Against Humanity Clone"
    API_VERSION: str = "0.1.0"
    API_DESCRIPTION: str = "Cross-platform multiplayer card game"
    CORS_ORIGINS: List[str] = ["http://localhost:8000"]
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    class Config:
        env_file = ".envs/.env.dev"
        case_sensitive = True


settings = Settings()
