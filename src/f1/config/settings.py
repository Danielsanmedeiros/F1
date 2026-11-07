"""Configurações do projeto lidas do ambiente ou de um arquivo `.env`."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "https://api.openf1.org/v1"
DEFAULT_REQUEST_INTERVAL_SECONDS = 2.0
DEFAULT_DATA_DIR = "data"
DEFAULT_LOG_LEVEL = "INFO"


@dataclass(frozen=True)
class Settings:
    """Configurações usadas pelo pipeline.

    Attributes:
        base_url: URL base da API OpenF1.
        request_interval_seconds: Intervalo mínimo entre chamadas à API.
        data_dir: Pasta dos arquivos Parquet e do banco DuckDB.
        log_level: Nível de log.
    """

    base_url: str
    request_interval_seconds: float
    data_dir: Path
    log_level: str

    @property
    def db_path(self) -> Path:
        """Caminho do arquivo do banco DuckDB."""
        return self.data_dir / "f1.duckdb"


def settings_from_env(env: Mapping[str, str]) -> Settings:
    """Monta as configurações a partir das variáveis informadas.

    Args:
        env: Variáveis de ambiente.

    Returns:
        Configurações validadas, com os valores padrão nas variáveis ausentes.

    Raises:
        ValueError: Se o intervalo entre chamadas não for um número não negativo.
    """
    raw_interval = env.get(
        "OPENF1_REQUEST_INTERVAL_SECONDS", str(DEFAULT_REQUEST_INTERVAL_SECONDS)
    )
    try:
        interval = float(raw_interval)
    except ValueError as exc:
        raise ValueError(
            f"OPENF1_REQUEST_INTERVAL_SECONDS inválido: {raw_interval!r}"
        ) from exc
    if interval < 0:
        raise ValueError("OPENF1_REQUEST_INTERVAL_SECONDS não pode ser negativo")

    return Settings(
        base_url=env.get("OPENF1_BASE_URL", DEFAULT_BASE_URL),
        request_interval_seconds=interval,
        data_dir=Path(env.get("F1_DATA_DIR", DEFAULT_DATA_DIR)),
        log_level=env.get("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper(),
    )
