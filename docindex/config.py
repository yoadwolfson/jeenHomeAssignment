"""Runtime configuration read from the environment and `.env`."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dotenv import dotenv_values

from docindex.errors import ConfigurationError

DEFAULT_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
GEMINI_API_KEY_VARIABLE = "GEMINI_API_KEY"
POSTGRES_URL_VARIABLE = "POSTGRES_URL"
SECRET_MASK = "***"


@dataclass(frozen=True)
class Settings:
    """The Gemini API key and the PostgreSQL connection URL."""

    gemini_api_key: str
    postgres_url: str

    @classmethod
    def from_env(cls, env_file: Path = DEFAULT_ENV_FILE, environ: Mapping[str, str] = os.environ) -> Settings:
        """Read settings from `env_file` once; variables already in `environ` take precedence."""
        file_values = {name: value for name, value in dotenv_values(env_file).items() if value is not None}
        merged = {**file_values, **environ}
        return cls(
            gemini_api_key=_require(merged, GEMINI_API_KEY_VARIABLE),
            postgres_url=_require(merged, POSTGRES_URL_VARIABLE),
        )

    def __repr__(self) -> str:
        return f"Settings(gemini_api_key='{SECRET_MASK}', postgres_url='{mask_url_password(self.postgres_url)}')"


def mask_url_password(url: str) -> str:
    """Return `url` with its password, if any, replaced by a mask."""
    parts = urlsplit(url)
    if parts.password is None:
        return url
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    netloc = f"{parts.username or ''}:{SECRET_MASK}@{host}{port}"
    return urlunsplit(parts._replace(netloc=netloc))


def _require(values: Mapping[str, str], name: str) -> str:
    value = values.get(name, "").strip()
    if not value:
        raise ConfigurationError(name)
    return value
