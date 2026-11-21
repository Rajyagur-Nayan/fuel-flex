import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

# Path definitions
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__)) # core
_APP_DIR = os.path.dirname(_CURRENT_DIR)                  # app
_BACKEND_ROOT = os.path.dirname(_APP_DIR)                 # backend


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Render Secret Files are mounted under /etc/secrets. Environment
        # variables still take precedence over both local and mounted files.
        env_file=(
            os.path.join(_BACKEND_ROOT, ".env"),
            ".env",
            "/etc/secrets/.env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True
    )

    PROJECT_NAME: str = "Fuelflux"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"

    # Directory Paths
    BASE_DIR: str = _APP_DIR
    BACKEND_DIR: str = _BACKEND_ROOT
    UPLOAD_DIR: str = os.path.join(_BACKEND_ROOT, "public", "uploads")

    # MongoDB Atlas
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "fuelflux"

    # Security
    SECRET_KEY: str = "change-this-secret-in-your-environment"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080

    # Azure (keep optional)
    AZURE_IOT_HUB_CONNECTION_STRING: Optional[str] = None

    # Razorpay
    RAZORPAY_KEY_ID: Optional[str] = None
    RAZORPAY_KEY_SECRET: Optional[str] = None
    RAZORPAY_WEBHOOK_SECRET: Optional[str] = None
    RAZORPAYX_ACCOUNT_NUMBER: Optional[str] = None

    # Google Authentication
    GOOGLE_CLIENT_ID: Optional[str] = None


settings = Settings()
