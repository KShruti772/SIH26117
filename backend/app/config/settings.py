from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    APP_ENV: str = "development"
    MODEL_MODE: str = "local"
    MODEL_DIR: str = "./models"
    DATABASE_URL: str = ""
    VECTOR_DB_PATH: str = "./vectorstore"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    SECRET_KEY: str = "CHANGE_ME"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    ALLOW_EXTERNAL_APIS: bool = False
    
    # Auth configuration variables
    AUTH_DB_PATH: str = "data/private/aegis_auth.db"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    
    # Safe default origins for development
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
        "http://localhost:8000",
        "http://127.0.0.1:8000"
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def model_post_init(self, __context):
        # Security Guard: Fail-safe check for missing production secret key
        if self.APP_ENV == "production" and self.SECRET_KEY == "CHANGE_ME":
            raise ValueError(
                "PRODUCTION SECURITY BREACH: SECRET_KEY environment variable is "
                "missing or set to the default 'CHANGE_ME' placeholder value."
            )

settings = Settings()
