import logging
from datetime import UTC, datetime

import polars as pl
import pytest

from f1.transform.normalize import (
    SchemaValidationError,
    flatten_session_result,
    normalize_records,
    select_finished_sessions,
)
from f1.transform.schemas import (
    ALL_SCHEMAS,
    LAPS,
    PIT,
    SESSION_RESULT,
    Column,
    EndpointSchema,
)

SIMPLE = EndpointSchema(
    name="simple",
    columns=(
        Column("id", pl.Int64),
        Column("value", pl.Float64),
        Column("date", pl.Datetime("us", "UTC")),
        Column("note", pl.String, required=False),
    ),
    key=("id",),
)


def simple_record(**overrides: object) -> dict[str, object]:
    return {"id": 1, "value": 1.5, "date": "2024-03-02T15:00:00+00:00"} | overrides


def test_normalize_converte_tipos_e_mantem_ordem_do_schema() -> None:
    df = normalize_records([simple_record(value=2)], SIMPLE)

    assert df.columns == ["id", "value", "date", "note"]
    assert df.schema["value"] == pl.Float64
    assert df["value"].to_list() == [2.0]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "2023-09-16T13:59:07.606000+00:00",
            datetime(2023, 9, 16, 13, 59, 7, 606000, tzinfo=UTC),
        ),
        ("2023-06-04T14:21:01+00:00", datetime(2023, 6, 4, 14, 21, 1, tzinfo=UTC)),
        ("2024-03-02T18:00:00+03:00", datetime(2024, 3, 2, 15, 0, tzinfo=UTC)),
        ("2024-03-02T15:00:00", datetime(2024, 3, 2, 15, 0, tzinfo=UTC)),
    ],
)
def test_normalize_converte_datas_para_utc(text: str, expected: datetime) -> None:
    df = normalize_records([simple_record(date=text)], SIMPLE)

    assert df["date"][0] == expected


def test_normalize_preenche_opcional_ausente_com_nulo() -> None:
    df = normalize_records([simple_record()], SIMPLE)

    assert df["note"].to_list() == [None]
    assert df.schema["note"] == pl.String


def test_normalize_aceita_campos_opcionais_de_pit_ausentes() -> None:
    record = {
        "session_key": 1,
        "meeting_key": 2,
        "driver_number": 44,
        "lap_number": 10,
        "date": "2023-05-07T18:42:25+00:00",
        "pit_duration": 22.2,
    }

    df = normalize_records([record], PIT)

    assert df["stop_duration"].to_list() == [None]
    assert df["pit_duration"].to_list() == [22.2]


def test_normalize_falha_com_coluna_obrigatoria_ausente() -> None:
    record = simple_record()
    del record["value"]

    with pytest.raises(SchemaValidationError, match=r"ausentes: \['value'\]"):
        normalize_records([record], SIMPLE)


def test_normalize_descarta_coluna_desconhecida_com_aviso(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        df = normalize_records([simple_record(extra=1)], SIMPLE)

    assert "extra" not in df.columns
    assert "colunas desconhecidas" in caplog.text
    assert "extra" in caplog.text


@pytest.mark.parametrize(
    "overrides",
    [{"id": "um"}, {"value": "rápido"}, {"date": "ontem"}, {"date": 20240302}],
)
def test_normalize_falha_com_tipo_invalido(overrides: dict[str, object]) -> None:
    with pytest.raises(SchemaValidationError, match="valor inválido"):
        normalize_records([simple_record(**overrides)], SIMPLE)


@pytest.mark.parametrize("schema", ALL_SCHEMAS, ids=lambda schema: schema.name)
def test_normalize_lista_vazia_gera_df_vazio_com_schema(
    schema: EndpointSchema,
) -> None:
    df = normalize_records([], schema)

    assert df.is_empty()
    assert df.columns == [column.name for column in schema.columns]


def test_normalize_laps_mantem_lista_de_segmentos_e_nulos() -> None:
    record = {
        "session_key": 1,
        "meeting_key": 2,
        "driver_number": 44,
        "lap_number": 1,
        "date_start": None,
        "lap_duration": None,
        "duration_sector_1": None,
        "duration_sector_2": 30.1,
        "duration_sector_3": 25,
        "i1_speed": 300,
        "i2_speed": None,
        "st_speed": 310,
        "is_pit_out_lap": True,
        "segments_sector_1": [2049, 2051],
        "segments_sector_2": None,
        "segments_sector_3": [],
    }

    df = normalize_records([record], LAPS)

    assert df.schema["segments_sector_1"] == pl.List(pl.Int64)
    assert df["segments_sector_1"].to_list() == [[2049, 2051]]
    assert df["duration_sector_3"].to_list() == [25.0]


def test_flatten_corrida_com_gap_numerico_e_em_voltas() -> None:
    flat = flatten_session_result(
        [
            {"driver_number": 1, "duration": 5400.1, "gap_to_leader": 0},
            {"driver_number": 2, "duration": None, "gap_to_leader": "+1 LAP"},
            {"driver_number": 3, "duration": None, "gap_to_leader": "+2 LAPS"},
            {"driver_number": 4, "duration": None, "gap_to_leader": None},
        ]
    )

    assert [(r["gap_to_leader"], r["laps_behind"]) for r in flat] == [
        (0.0, None),
        (None, 1),
        (None, 2),
        (None, None),
    ]


def test_flatten_classificacao_separa_q1_q2_q3() -> None:
    flat = flatten_session_result(
        [
            {
                "driver_number": 1,
                "duration": [90.1, 89.5, None],
                "gap_to_leader": [0.1, 0, None],
            }
        ]
    )[0]

    assert flat["duration_q1"] == 90.1
    assert flat["duration_q3"] is None
    assert flat["gap_to_leader_q2"] == 0.0
    assert "duration" not in flat
    assert "gap_to_leader" not in flat


@pytest.mark.parametrize(
    "record",
    [
        {"gap_to_leader": "DESCONHECIDO"},
        {"gap_to_leader": True},
        {"duration": [1.0, 2.0]},
        {"gap_to_leader": ["texto", 1.0, 2.0]},
    ],
)
def test_flatten_rejeita_formato_desconhecido(record: dict[str, object]) -> None:
    with pytest.raises(SchemaValidationError):
        flatten_session_result([record])


def test_normalize_session_result_gera_colunas_estaveis() -> None:
    base = {
        "session_key": 1,
        "meeting_key": 2,
        "position": 1,
        "number_of_laps": 57,
        "dnf": False,
        "dns": False,
        "dsq": False,
    }

    df = normalize_records(
        [
            base
            | {"driver_number": 1, "duration": 54, "gap_to_leader": 0, "points": 26},
            base | {"driver_number": 2, "duration": 5401, "gap_to_leader": "+1 LAP"},
        ],
        SESSION_RESULT,
    )

    assert df["points"].to_list() == [26.0, None]
    assert df["gap_to_leader"].to_list() == [0.0, None]
    assert df["laps_behind"].to_list() == [None, 1]
    assert df["duration_q1"].to_list() == [None, None]


def test_select_finished_ignora_futuras_canceladas_e_sem_fim() -> None:
    now = datetime(2024, 6, 1, tzinfo=UTC)
    sessions = pl.DataFrame(
        {
            "session_key": [3, 1, 2, 4, 5],
            "date_end": [
                datetime(2024, 5, 1, tzinfo=UTC),
                datetime(2024, 4, 1, tzinfo=UTC),
                datetime(2024, 7, 1, tzinfo=UTC),
                datetime(2024, 3, 1, tzinfo=UTC),
                None,
            ],
            "is_cancelled": [None, False, False, True, False],
        },
        schema_overrides={
            "date_end": pl.Datetime("us", "UTC"),
            "is_cancelled": pl.Boolean,
        },
    )

    assert select_finished_sessions(sessions, now) == [1, 3]
