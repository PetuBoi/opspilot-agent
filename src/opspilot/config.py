"""Environment configuration and redacted structured operational logging."""

import json
import logging
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPSPILOT_", env_file=".env", extra="ignore")
    data_dir: Path = Path("data/runtime")
    api_token: SecretStr = SecretStr("")
    classifier_dataset: str = "demo"
    live_enabled: bool = False
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_timeout: float = Field(default=20, gt=0, le=120)
    top_k: int = Field(default=5, ge=1, le=20)
    chunk_size: int = Field(default=900, ge=100, le=4000)

    @property
    def db_path(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir / "opspilot.sqlite"


def log_event(event: str, **fields: str | int | float) -> None:
    # Callers supply IDs/counts only; never serialize user text, settings or provider errors.
    logging.getLogger("opspilot").info(json.dumps({"event": event, **fields}))
