"""Orquestração da carga e linha de comando `f1-ingest`."""

import argparse
import logging
import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import duckdb
import polars as pl
from dotenv import load_dotenv

from f1.config.settings import settings_from_env
from f1.extract.client import ApiAccessError, ApiRequestError, OpenF1Client
from f1.load.duckdb import refresh_views
from f1.load.parquet import partition_path, write_partition
from f1.transform.normalize import (
    SchemaValidationError,
    normalize_records,
    select_finished_sessions,
)
from f1.transform.quality import DataQualityError, enforce_quality
from f1.transform.schemas import (
    ALL_SCHEMAS,
    MEETINGS,
    SESSION_SCHEMAS,
    SESSIONS,
    EndpointSchema,
)

logger = logging.getLogger(__name__)

FIRST_YEAR = 2023

_PARTITION_ERRORS = (
    ApiRequestError,
    SchemaValidationError,
    DataQualityError,
    OSError,
    pl.exceptions.PolarsError,
)


class RecordSource(Protocol):
    """Origem dos registros, implementada por `OpenF1Client`."""

    def get(self, endpoint: str, **params: str | int) -> list[dict[str, Any]]:
        """Busca os registros de um endpoint.

        Args:
            endpoint: Nome do endpoint.
            **params: Filtros da consulta.

        Returns:
            Registros retornados.
        """
        ...


@dataclass(frozen=True)
class PartitionFailure:
    """Falha ao carregar uma partição.

    Attributes:
        path: Caminho da partição ou nome da etapa que falhou.
        error: Descrição do erro.
    """

    path: str
    error: str


@dataclass
class IngestReport:
    """Resultado de uma carga.

    Attributes:
        written: Partições gravadas.
        skipped: Partições existentes, ignoradas.
        failures: Partições que falharam.
        aborted_reason: Motivo da interrupção antecipada, se houver.
    """

    written: int = 0
    skipped: int = 0
    failures: list[PartitionFailure] = field(default_factory=list)
    aborted_reason: str | None = None

    @property
    def succeeded(self) -> bool:
        """Se a carga terminou sem falhas nem interrupção."""
        return not self.failures and self.aborted_reason is None


def run_ingest(
    source: RecordSource,
    data_dir: Path,
    db_path: Path,
    years: Iterable[int],
    *,
    force: bool = False,
    now: datetime,
) -> IngestReport:
    """Carrega temporadas em Parquet e recria as views no DuckDB.

    `meetings` e `sessions` são sempre buscadas de novo, pois definem o calendário e
    mudam durante a temporada. As demais tabelas são carregadas por sessão, ignorando
    as partições existentes, salvo com `force`. Uma partição com falha não impede as
    demais. Uma recusa de acesso interrompe a carga, que pode ser repetida depois para
    retomar de onde parou.

    Args:
        source: Origem dos registros.
        data_dir: Pasta raiz dos dados.
        db_path: Caminho do banco DuckDB.
        years: Temporadas a carregar.
        force: Se as partições existentes devem ser recarregadas.
        now: Instante de referência para selecionar as sessões encerradas.

    Returns:
        Resumo da carga.
    """
    report = IngestReport()
    try:
        for year in years:
            _ingest_year(source, data_dir, year, force, now, report)
    except ApiAccessError as exc:
        report.aborted_reason = str(exc)

    try:
        refresh_views(db_path, data_dir, [schema.name for schema in ALL_SCHEMAS])
    except (duckdb.Error, OSError) as exc:
        report.failures.append(PartitionFailure("views do DuckDB", str(exc)))
    return report


def _ingest_year(
    source: RecordSource,
    data_dir: Path,
    year: int,
    force: bool,
    now: datetime,
    report: IngestReport,
) -> None:
    _load_guarded(source, MEETINGS, data_dir, {"year": year}, {"year": year}, report)
    sessions = _load_guarded(
        source, SESSIONS, data_dir, {"year": year}, {"year": year}, report
    )
    if sessions is None:
        return

    session_keys = select_finished_sessions(sessions, now)
    logger.info("Temporada %d: %d sessões encerradas", year, len(session_keys))
    for session_key in session_keys:
        for schema in SESSION_SCHEMAS:
            partitions = {"year": year, "session_key": session_key}
            if (
                not force
                and partition_path(data_dir, schema.name, **partitions).exists()
            ):
                report.skipped += 1
                continue
            _load_guarded(
                source,
                schema,
                data_dir,
                partitions,
                {"session_key": session_key},
                report,
            )


def _load_guarded(
    source: RecordSource,
    schema: EndpointSchema,
    data_dir: Path,
    partitions: dict[str, int],
    params: dict[str, int],
    report: IngestReport,
) -> pl.DataFrame | None:
    path = partition_path(data_dir, schema.name, **partitions)
    try:
        records = source.get(schema.name, **params)
        df = enforce_quality(normalize_records(records, schema), schema)
        write_partition(df, path)
    except _PARTITION_ERRORS as exc:
        logger.error("Falha em %s: %s", path, exc)
        report.failures.append(PartitionFailure(str(path), str(exc)))
        return None
    report.written += 1
    logger.info("Gravada %s (%d linhas)", path, df.height)
    return df


def _parse_year(value: str) -> int:
    try:
        year = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"ano inválido: {value!r}") from exc
    if year < FIRST_YEAR:
        raise argparse.ArgumentTypeError(
            f"a API só tem dados a partir de {FIRST_YEAR}: {year}"
        )
    return year


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="f1-ingest",
        description="Carrega dados históricos da OpenF1 em Parquet e DuckDB.",
    )
    parser.add_argument(
        "--year",
        dest="years",
        action="append",
        type=_parse_year,
        required=True,
        help="temporada a carregar, a partir de 2023; pode ser repetido",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="recarrega as partições existentes",
    )
    return parser


def _log_report(report: IngestReport) -> None:
    logger.info(
        "Resumo: %d partições gravadas, %d ignoradas, %d falhas",
        report.written,
        report.skipped,
        len(report.failures),
    )
    for failure in report.failures:
        logger.error("Falhou: %s: %s", failure.path, failure.error)
    if report.aborted_reason:
        logger.error(
            "Carga interrompida: %s. Repita o comando depois para retomar.",
            report.aborted_reason,
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Executa a linha de comando `f1-ingest`.

    Args:
        argv: Argumentos da linha de comando. Por padrão, usa os do processo.

    Returns:
        0 em caso de sucesso e 1 se alguma partição falhar ou a carga for interrompida.
    """
    args = _build_parser().parse_args(argv)
    load_dotenv()
    settings = settings_from_env(os.environ)
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    with OpenF1Client(settings.base_url, settings.request_interval_seconds) as client:
        report = run_ingest(
            client,
            settings.data_dir,
            settings.db_path,
            dict.fromkeys(args.years),
            force=args.force,
            now=datetime.now(UTC),
        )
    _log_report(report)
    return 0 if report.succeeded else 1
