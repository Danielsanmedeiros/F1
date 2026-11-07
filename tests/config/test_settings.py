from pathlib import Path

import pytest

from f1.config.settings import settings_from_env


def test_settings_usam_valores_padrao() -> None:
    settings = settings_from_env({})

    assert settings.base_url == "https://api.openf1.org/v1"
    assert settings.request_interval_seconds == 2.0
    assert settings.data_dir == Path("data")
    assert settings.db_path == Path("data") / "f1.duckdb"
    assert settings.log_level == "INFO"


def test_settings_leem_variaveis() -> None:
    settings = settings_from_env(
        {
            "OPENF1_BASE_URL": "http://local/v1",
            "OPENF1_REQUEST_INTERVAL_SECONDS": "0.5",
            "F1_DATA_DIR": "outro",
            "LOG_LEVEL": "debug",
        }
    )

    assert settings.base_url == "http://local/v1"
    assert settings.request_interval_seconds == 0.5
    assert settings.data_dir == Path("outro")
    assert settings.log_level == "DEBUG"


@pytest.mark.parametrize("value", ["abc", "-1"])
def test_settings_rejeitam_intervalo_invalido(value: str) -> None:
    with pytest.raises(ValueError, match="OPENF1_REQUEST_INTERVAL_SECONDS"):
        settings_from_env({"OPENF1_REQUEST_INTERVAL_SECONDS": value})
