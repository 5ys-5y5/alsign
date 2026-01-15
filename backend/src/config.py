"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database Configuration
    DATABASE_URL: str | None = None
    DB_POOL_MIN_SIZE: int = 5
    DB_POOL_MAX_SIZE: int = 30  # 20 ticker workers × ~1.5 avg connections (conservative for DB CPU)

    # External API Configuration
    FMP_API_KEY: str
    FMP_BASE_URL: str = "https://financialmodelingprep.com/api/v3"
    FMP_RATE_LIMIT: int = 250

    # Application Configuration
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"
    SUPABASE_JWT_SECRET: str | None = None

    # CORS Settings
    CORS_ORIGINS: str = '["http://localhost:3000","http://localhost:5173"]'

    # Batch Configuration
    DB_UPSERT_BATCH_SIZE: int = 1000
    API_BATCH_SIZE_INITIAL: int = 50

    class Config:
        env_file = ".env"
        case_sensitive = True

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from JSON string."""
        return json.loads(self.CORS_ORIGINS)


# Global settings instance
settings = Settings()
