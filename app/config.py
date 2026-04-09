from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./irrigation.db"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    DEBUG: bool = True
    API_KEY: str = ""

    # Anomaly thresholds
    MOISTURE_SPIKE_THRESHOLD: float = 20.0
    MOISTURE_SATURATION_HOURS: int = 6
    TEMP_STRESS_HIGH: float = 38.0
    TEMP_STRESS_LOW: float = 5.0

    # Prediction model
    LOOKBACK_READINGS: int = 24
    MIN_READINGS_FOR_PREDICTION: int = 5

    # Trefle plant API
    TREFLE_API_TOKEN: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
