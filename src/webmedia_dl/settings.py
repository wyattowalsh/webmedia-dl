"""Pydantic settings for the local worker. No mandatory cloud, no default telemetry."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from webmedia_dl.paths import worker_data_dir


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WEBMEDIA_DL_",
        extra="forbid",
    )

    bind_host: str = "127.0.0.1"
    bind_port: int = 8765
    data_dir: Path | None = None
    default_profile: str = "personal-full"
    telemetry: bool = False
    log_json: bool = False

    token_path: Path | None = Field(default=None)

    def resolved_data_dir(self) -> Path:
        return worker_data_dir(self.data_dir)
