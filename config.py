from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    UBER_SID: str
    UBER_CSID: str
    DBT_PROFILES_DIR: str
    UBER_DUCKDB: str
    GOOGLE_SERVICE_ACCOUNT: str
    GOOGLE_API_KEY: str
    SHEET_ID: int

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent / ".env", extra="ignore"
    )


def load_config() -> Config:
    return Config()
