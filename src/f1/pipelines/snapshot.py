"""Publicação e recuperação do snapshot dos dados usado pelo dashboard online."""

import argparse
import logging
import os
from collections.abc import Sequence
from pathlib import Path

import httpx
from dotenv import load_dotenv

from f1.config.settings import settings_from_env
from f1.extract.snapshot import download_snapshot
from f1.load.duckdb import refresh_views
from f1.load.snapshot import write_snapshot
from f1.transform.schemas import ALL_SCHEMAS

DEFAULT_OUTPUT = Path("dist") / "f1-data.zip"

logger = logging.getLogger(__name__)


def ensure_data(
    url: str,
    data_dir: Path,
    db_path: Path,
    transport: httpx.BaseTransport | None = None,
) -> None:
    """Baixa o snapshot e cria as views, se o banco ainda não existir.

    O banco é criado por último: se o download falhar, a próxima chamada recomeça.

    Args:
        url: Endereço do snapshot.
        data_dir: Pasta raiz dos dados.
        db_path: Caminho do banco DuckDB.
        transport: Transporte HTTP alternativo, usado nos testes.
    """
    if db_path.exists():
        return
    download_snapshot(url, data_dir, transport)
    refresh_views(db_path, data_dir, [schema.name for schema in ALL_SCHEMAS])


def main(argv: Sequence[str] | None = None) -> int:
    """Executa a linha de comando `f1-snapshot`, que gera o zip a ser publicado.

    Args:
        argv: Argumentos da linha de comando. Por padrão, usa os do processo.

    Returns:
        0 em caso de sucesso e 1 se não houver dados para compactar.
    """
    parser = argparse.ArgumentParser(
        description="Gera o snapshot dos dados para o dashboard online."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Arquivo zip de saída (padrão: {DEFAULT_OUTPUT.as_posix()}).",
    )
    args = parser.parse_args(argv)

    load_dotenv()
    settings = settings_from_env(os.environ)
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        count = write_snapshot(settings.data_dir, args.output)
    except ValueError as exc:
        logger.error("%s. Carregue os dados com f1-ingest.", exc)
        return 1
    logger.info("Snapshot gerado em %s com %d arquivos.", args.output, count)
    return 0
