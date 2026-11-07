"""Conversão dos registros da API em DataFrames tipados."""

import logging
import re
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

import polars as pl

from f1.transform.schemas import Column, EndpointSchema

logger = logging.getLogger(__name__)

Record = dict[str, Any]

_LAPPED_GAP = re.compile(r"^\+(\d+) LAPS?$")
_PHASES = ("q1", "q2", "q3")


class SchemaValidationError(ValueError):
    """Os registros não seguem o schema do endpoint."""


def normalize_records(
    records: Sequence[Record], schema: EndpointSchema
) -> pl.DataFrame:
    """Converte registros da API em um DataFrame com as colunas do schema.

    Colunas opcionais ausentes são criadas com nulos. Colunas desconhecidas geram um
    aviso e são descartadas. Uma lista vazia gera um DataFrame vazio com o schema.

    Args:
        records: Registros retornados pela API.
        schema: Contrato do endpoint.

    Returns:
        DataFrame com as colunas e os tipos do schema.

    Raises:
        SchemaValidationError: Se faltar uma coluna obrigatória ou se algum valor
            tiver tipo inválido.
    """
    prepare = _PREPARERS.get(schema.name)
    prepared = prepare(records) if prepare else records
    if prepared:
        _check_columns(prepared, schema)
    return pl.DataFrame([_build_series(prepared, column) for column in schema.columns])


def flatten_session_result(records: Sequence[Record]) -> list[Record]:
    """Separa os campos de formato variável de `session_result` em colunas estáveis.

    `duration` e `gap_to_leader` podem ser número, nulo ou uma lista com os valores
    de Q1, Q2 e Q3. `gap_to_leader` também pode ser um texto como `+1 LAP`.

    Args:
        records: Registros originais.

    Returns:
        Registros com `duration`, `gap_to_leader` e `laps_behind` nas sessões de valor
        único, e com `duration_q1` a `duration_q3` e `gap_to_leader_q1` a
        `gap_to_leader_q3` nas de classificação.

    Raises:
        SchemaValidationError: Se algum valor tiver formato desconhecido.
    """
    return [_flatten_result(record) for record in records]


def select_finished_sessions(sessions: pl.DataFrame, now: datetime) -> list[int]:
    """Seleciona as sessões encerradas e não canceladas.

    Args:
        sessions: Tabela `sessions` normalizada.
        now: Instante de referência, com fuso horário.

    Returns:
        Valores de `session_key` em ordem crescente.
    """
    selected = sessions.filter(
        (pl.col("date_end") < now) & ~pl.col("is_cancelled").fill_null(False)
    )
    return sorted(selected["session_key"].to_list())


def _check_columns(records: Sequence[Record], schema: EndpointSchema) -> None:
    received = {name for record in records for name in record}
    expected = {column.name for column in schema.columns}

    missing = sorted(
        column.name
        for column in schema.columns
        if column.required and column.name not in received
    )
    if missing:
        raise SchemaValidationError(
            f"{schema.name}: colunas obrigatórias ausentes: {missing}"
        )

    unknown = sorted(received - expected)
    if unknown:
        logger.warning(
            "%s: colunas desconhecidas descartadas: %s", schema.name, unknown
        )


def _build_series(records: Sequence[Record], column: Column) -> pl.Series:
    values = [record.get(column.name) for record in records]
    try:
        if isinstance(column.dtype, pl.Datetime):
            values = [_parse_datetime(value) for value in values]
        return pl.Series(column.name, values, dtype=column.dtype, strict=True)
    except (TypeError, ValueError, OverflowError, pl.exceptions.PolarsError) as exc:
        raise SchemaValidationError(
            f"coluna {column.name}: valor inválido para {column.dtype}: {exc}"
        ) from exc


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"data deve ser texto, recebido {value!r}")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _flatten_result(record: Record) -> Record:
    flat = {
        name: value
        for name, value in record.items()
        if name not in ("duration", "gap_to_leader")
    }

    duration = record.get("duration")
    if isinstance(duration, list):
        flat |= _by_phase("duration", duration)
    else:
        flat["duration"] = duration

    gap = record.get("gap_to_leader")
    if isinstance(gap, list):
        seconds_by_phase = [_parse_gap(value)[0] for value in gap]
        flat |= _by_phase("gap_to_leader", seconds_by_phase)
    else:
        flat["gap_to_leader"], flat["laps_behind"] = _parse_gap(gap)
    return flat


def _by_phase(name: str, values: list[Any]) -> Record:
    if len(values) != len(_PHASES):
        raise SchemaValidationError(f"{name}: esperados 3 valores, recebido {values!r}")
    return {
        f"{name}_{phase}": value for phase, value in zip(_PHASES, values, strict=True)
    }


def _parse_gap(value: Any) -> tuple[float | None, int | None]:
    if value is None:
        return None, None
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value), None
    if isinstance(value, str) and (match := _LAPPED_GAP.match(value)):
        return None, int(match[1])
    raise SchemaValidationError(f"gap_to_leader: valor inválido: {value!r}")


_PREPARERS: dict[str, Callable[[Sequence[Record]], Sequence[Record]]] = {
    "session_result": flatten_session_result,
}
