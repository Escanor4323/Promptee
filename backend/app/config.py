"""Pydantic-settings configuration for the Promptee backend."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    milvus_host: str = "localhost"
    milvus_port: int = 19530
    fastapi_host: str = "0.0.0.0"
    fastapi_port: int = 8000
    sqlite_db_path: str = "./data/promptee.db"
    embedding_model_name: str = "all-MiniLM-L6-v2"
    log_level: str = "INFO"


def get_settings() -> Settings:
    return Settings()
