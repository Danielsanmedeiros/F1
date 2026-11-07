"""Colunas, tipos e chaves de cada endpoint da OpenF1."""

from dataclasses import dataclass

import polars as pl

PolarsType = pl.DataType | type[pl.DataType]

_DATETIME = pl.Datetime("us", "UTC")
_SEGMENTS = pl.List(pl.Int64)


@dataclass(frozen=True)
class Column:
    """Coluna de um endpoint.

    Attributes:
        name: Nome da coluna.
        dtype: Tipo no DataFrame.
        required: Se a falta da coluna em toda a resposta invalida a partição.
    """

    name: str
    dtype: PolarsType
    required: bool = True


@dataclass(frozen=True)
class EndpointSchema:
    """Contrato de um endpoint.

    Attributes:
        name: Nome do endpoint e da tabela.
        columns: Colunas, na ordem de gravação.
        key: Colunas da chave. Vazia quando não há chave natural.
    """

    name: str
    columns: tuple[Column, ...]
    key: tuple[str, ...]


def _columns(
    dtype: PolarsType, *names: str, required: bool = True
) -> tuple[Column, ...]:
    return tuple(Column(name, dtype, required) for name in names)


MEETINGS = EndpointSchema(
    name="meetings",
    columns=(
        *_columns(pl.Int64, "meeting_key", "year", "circuit_key", "country_key"),
        *_columns(_DATETIME, "date_start", "date_end"),
        *_columns(
            pl.String,
            "meeting_name",
            "meeting_official_name",
            "location",
            "country_code",
            "country_name",
            "circuit_short_name",
            "gmt_offset",
        ),
        *_columns(
            pl.String,
            "circuit_type",
            "circuit_image",
            "circuit_info_url",
            "country_flag",
            required=False,
        ),
        Column("is_cancelled", pl.Boolean, required=False),
    ),
    key=("meeting_key",),
)

SESSIONS = EndpointSchema(
    name="sessions",
    columns=(
        *_columns(
            pl.Int64, "session_key", "meeting_key", "year", "circuit_key", "country_key"
        ),
        *_columns(_DATETIME, "date_start", "date_end"),
        *_columns(
            pl.String,
            "session_name",
            "session_type",
            "location",
            "country_code",
            "country_name",
            "circuit_short_name",
            "gmt_offset",
        ),
        Column("is_cancelled", pl.Boolean, required=False),
    ),
    key=("session_key",),
)

DRIVERS = EndpointSchema(
    name="drivers",
    columns=(
        *_columns(pl.Int64, "session_key", "meeting_key", "driver_number"),
        *_columns(
            pl.String,
            "broadcast_name",
            "full_name",
            "first_name",
            "last_name",
            "name_acronym",
            "team_name",
            "team_colour",
            "headshot_url",
        ),
        # Depreciado: será removido pela API após a temporada de 2026.
        Column("country_code", pl.String, required=False),
    ),
    key=("session_key", "driver_number"),
)

LAPS = EndpointSchema(
    name="laps",
    columns=(
        *_columns(
            pl.Int64, "session_key", "meeting_key", "driver_number", "lap_number"
        ),
        Column("date_start", _DATETIME),
        *_columns(
            pl.Float64,
            "lap_duration",
            "duration_sector_1",
            "duration_sector_2",
            "duration_sector_3",
        ),
        *_columns(pl.Int64, "i1_speed", "i2_speed", "st_speed"),
        Column("is_pit_out_lap", pl.Boolean),
        *_columns(
            _SEGMENTS, "segments_sector_1", "segments_sector_2", "segments_sector_3"
        ),
    ),
    key=("session_key", "driver_number", "lap_number"),
)

STINTS = EndpointSchema(
    name="stints",
    columns=(
        *_columns(
            pl.Int64,
            "session_key",
            "meeting_key",
            "driver_number",
            "stint_number",
            "lap_start",
            "lap_end",
            "tyre_age_at_start",
        ),
        Column("compound", pl.String),
    ),
    key=("session_key", "driver_number", "stint_number"),
)

PIT = EndpointSchema(
    name="pit",
    columns=(
        *_columns(
            pl.Int64, "session_key", "meeting_key", "driver_number", "lap_number"
        ),
        Column("date", _DATETIME),
        # Só existe em dados recentes da API.
        Column("lane_duration", pl.Float64, required=False),
        # Depreciado: será removido pela API após a temporada de 2026.
        Column("pit_duration", pl.Float64, required=False),
        # Só existe a partir do GP dos EUA de 2024.
        Column("stop_duration", pl.Float64, required=False),
    ),
    key=("session_key", "driver_number", "date"),
)

POSITION = EndpointSchema(
    name="position",
    columns=(
        *_columns(pl.Int64, "session_key", "meeting_key", "driver_number", "position"),
        Column("date", _DATETIME),
    ),
    key=("session_key", "driver_number", "date"),
)

SESSION_RESULT = EndpointSchema(
    name="session_result",
    columns=(
        *_columns(pl.Int64, "session_key", "meeting_key", "driver_number"),
        *_columns(pl.Int64, "position", "number_of_laps"),
        *_columns(pl.Boolean, "dnf", "dns", "dsq"),
        # Campos de formato variável: ver normalize.flatten_session_result.
        *_columns(
            pl.Float64,
            "duration",
            "duration_q1",
            "duration_q2",
            "duration_q3",
            "gap_to_leader",
            "gap_to_leader_q1",
            "gap_to_leader_q2",
            "gap_to_leader_q3",
            required=False,
        ),
        Column("laps_behind", pl.Int64, required=False),
        # Não documentado pela API. Só aparece nas corridas.
        Column("points", pl.Float64, required=False),
    ),
    key=("session_key", "driver_number"),
)

STARTING_GRID = EndpointSchema(
    name="starting_grid",
    columns=(
        *_columns(pl.Int64, "session_key", "meeting_key", "driver_number", "position"),
        Column("lap_duration", pl.Float64),
    ),
    key=("session_key", "driver_number"),
)

WEATHER = EndpointSchema(
    name="weather",
    columns=(
        *_columns(pl.Int64, "session_key", "meeting_key"),
        Column("date", _DATETIME),
        *_columns(
            pl.Float64,
            "air_temperature",
            "track_temperature",
            "humidity",
            "pressure",
            "wind_speed",
        ),
        *_columns(pl.Int64, "rainfall", "wind_direction"),
    ),
    key=("session_key", "date"),
)

RACE_CONTROL = EndpointSchema(
    name="race_control",
    columns=(
        *_columns(pl.Int64, "session_key", "meeting_key"),
        Column("date", _DATETIME),
        *_columns(pl.String, "category", "flag", "scope", "message"),
        *_columns(
            pl.Int64, "driver_number", "lap_number", "sector", "qualifying_phase"
        ),
    ),
    key=(),
)

CALENDAR_SCHEMAS = (MEETINGS, SESSIONS)
"""Tabelas particionadas por ano, que definem as sessões a carregar."""

SESSION_SCHEMAS = (
    DRIVERS,
    LAPS,
    STINTS,
    PIT,
    POSITION,
    SESSION_RESULT,
    STARTING_GRID,
    WEATHER,
    RACE_CONTROL,
)
"""Tabelas particionadas por ano e sessão."""

ALL_SCHEMAS = (*CALENDAR_SCHEMAS, *SESSION_SCHEMAS)
"""Todas as tabelas do projeto."""
