"""Application settings, loaded from environment / .env."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    # Google Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    gemini_fallback_model: str = "gemini-3.5-flash-lite"
    gemini_use_fallback_model: bool = False

    # Storage
    data_dir: str = "./data"
    database_url: str = "sqlite:///strategies.db"

    # HTTP
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,https://easybacktest.vercel.app,https://easybacktest-3stm.vercel.app"

    # Jobs
    enable_scheduler: bool = False

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir).expanduser().resolve()

    @property
    def ohlcv_path(self) -> Path:
        return self.data_path / "ohlcv"

    @property
    def tickers_path(self) -> Path:
        return self.data_path / "tickers"

    @property
    def sqlite_file(self) -> Path:
        # sqlite:///relative.db  or  sqlite:////absolute.db
        raw = self.database_url.replace("sqlite:///", "", 1)
        p = Path(raw)
        return p if p.is_absolute() else (Path.cwd() / p).resolve()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def active_model(self) -> str:
        return (
            self.gemini_fallback_model
            if self.gemini_use_fallback_model
            else self.gemini_model
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
