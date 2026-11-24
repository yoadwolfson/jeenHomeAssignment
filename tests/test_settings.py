"""Settings.from_env: .env loading, environment precedence, secret masking."""

from pathlib import Path

import pytest

from docindex.config import Settings
from docindex.errors import ConfigurationError

API_KEY = "AIza-secret-key-value"
DB_PASSWORD = "s3cret-pass"
DB_URL = f"postgresql://postgres:{DB_PASSWORD}@db.example:5432/docindex"


def write_env_file(directory: Path, content: str) -> Path:
    env_file = directory / ".env"
    env_file.write_text(content, encoding="utf-8")
    return env_file


def test_values_are_read_from_the_env_file(tmp_path: Path) -> None:
    env_file = write_env_file(tmp_path, f"GEMINI_API_KEY={API_KEY}\nPOSTGRES_URL={DB_URL}\n")

    settings = Settings.from_env(env_file=env_file, environ={})

    assert settings.gemini_api_key == API_KEY
    assert settings.postgres_url == DB_URL


def test_variables_already_in_the_environment_win_over_the_env_file(tmp_path: Path) -> None:
    env_file = write_env_file(tmp_path, f"GEMINI_API_KEY={API_KEY}\nPOSTGRES_URL={DB_URL}\n")

    settings = Settings.from_env(env_file=env_file, environ={"GEMINI_API_KEY": "from-environment"})

    assert settings.gemini_api_key == "from-environment"
    assert settings.postgres_url == DB_URL


def test_a_missing_env_file_falls_back_to_the_environment(tmp_path: Path) -> None:
    settings = Settings.from_env(
        env_file=tmp_path / "absent.env", environ={"GEMINI_API_KEY": API_KEY, "POSTGRES_URL": DB_URL}
    )

    assert settings.gemini_api_key == API_KEY


def test_a_missing_variable_raises_configuration_error_naming_it(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError) as raised:
        Settings.from_env(env_file=tmp_path / "absent.env", environ={"GEMINI_API_KEY": API_KEY})

    assert "POSTGRES_URL" in raised.value.message


def test_repr_masks_the_api_key_and_the_database_password() -> None:
    settings = Settings(gemini_api_key=API_KEY, postgres_url=DB_URL)

    for rendered in (repr(settings), str(settings)):
        assert API_KEY not in rendered
        assert DB_PASSWORD not in rendered
        assert "db.example" in rendered
