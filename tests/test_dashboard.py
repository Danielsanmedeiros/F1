from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import duckdb
import polars as pl
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

SCRIPT = str(Path(__file__).parents[1] / "src" / "f1" / "dashboard.py")
PAST = datetime(2024, 3, 2, 15, 0, tzinfo=UTC)
FUTURE = datetime.now(UTC) + timedelta(days=30)
DATETIME = pl.Datetime("us", "UTC")


def session_row(key: int, name: str, kind: str, end: datetime = PAST) -> dict[str, Any]:
    return {
        "session_key": key,
        "meeting_key": 1,
        "year": 2024,
        "session_name": name,
        "session_type": kind,
        "location": "Sakhir",
        "date_start": PAST,
        "date_end": end,
        "is_cancelled": False,
    }


def tables(sessions: list[dict[str, Any]]) -> dict[str, pl.DataFrame]:
    return {
        "sessions": pl.DataFrame(
            sessions,
            schema_overrides={"date_start": DATETIME, "date_end": DATETIME},
        ),
        "meetings": pl.DataFrame(
            {"meeting_key": [1], "meeting_name": ["GP do Bahrein"]}
        ),
        "drivers": pl.DataFrame(
            {
                "driver_number": [1, 2],
                "name_acronym": ["VER", "COL"],
                "full_name": ["Max VERSTAPPEN", "Franco COLAPINTO"],
                "team_name": ["Red Bull Racing", "Williams"],
                "team_colour": ["3671c6", "64c4ff"],
                "headshot_url": ["https://media.test/ver.png", None],
            }
        ),
        "session_result": pl.DataFrame(
            {
                "driver_number": [1, 2],
                "position": [1, None],
                "number_of_laps": [2, 1],
                "points": [25.0, 0.0],
                "dnf": [False, True],
                "dns": [False, False],
                "dsq": [False, False],
                "duration": [5504.742, None],
                "duration_q1": [None, None],
                "duration_q2": [None, None],
                "duration_q3": [None, None],
                "gap_to_leader": [0.0, None],
                "laps_behind": [None, None],
            },
            schema_overrides={
                "duration_q1": pl.Float64,
                "duration_q2": pl.Float64,
                "duration_q3": pl.Float64,
                "laps_behind": pl.Int64,
            },
        ),
        "laps": pl.DataFrame(
            {
                "driver_number": [1, 1, 2],
                "lap_number": [1, 2, 1],
                "lap_duration": [90.0, 91.0, 92.0],
                "is_pit_out_lap": [False, False, False],
                "date_start": [PAST, PAST + timedelta(minutes=2), PAST],
            },
            schema_overrides={"date_start": DATETIME},
        ),
        "position": pl.DataFrame(
            {
                "driver_number": [1, 2],
                "date": [PAST, PAST],
                "position": [1, 2],
            },
            schema_overrides={"date": DATETIME},
        ),
        "stints": pl.DataFrame(
            {
                "driver_number": [1, 2],
                "stint_number": [1, 1],
                "compound": ["SOFT", "HARD"],
                "lap_start": [1, 1],
                "lap_end": [2, 1],
                "tyre_age_at_start": [0, 3],
            }
        ),
    }


@pytest.fixture(autouse=True)
def isolated_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    monkeypatch.setenv("F1_DATA_DIR", str(tmp_path))
    st.cache_data.clear()
    yield tmp_path
    st.cache_data.clear()


def run_app(data: dict[str, pl.DataFrame], data_dir: Path) -> AppTest:
    (data_dir / "f1.duckdb").touch()

    def fake_read(_: Path, table: str, **__: int) -> pl.DataFrame:
        return data[table]

    with patch("f1.extract.warehouse.read_table", side_effect=fake_read):
        return AppTest.from_file(SCRIPT, default_timeout=60).run()


def test_dashboard_sem_banco_orienta_a_carga() -> None:
    app = AppTest.from_file(SCRIPT, default_timeout=60).run()

    assert not app.exception
    assert "ainda não existe" in app.error[0].value
    assert "f1-ingest" in app.code[0].value


def test_dashboard_mostra_corrida_por_padrao(isolated_data_dir: Path) -> None:
    data = tables(
        [
            session_row(10, "Practice 1", "Practice"),
            session_row(11, "Race", "Race"),
            session_row(12, "Futura", "Race", end=FUTURE),
        ]
    )

    app = run_app(data, isolated_data_dir)

    assert not app.exception
    assert app.title[0].value == "GP do Bahrein: Race"
    assert app.selectbox[2].options == ["Practice 1", "Race"]
    assert [item.value for item in app.subheader] == [
        "Classificação",
        "Ritmo por volta",
        "Evolução das posições",
        "Estratégia de pneus",
    ]
    assert app.multiselect[0].value == [1, 2]
    assert app.multiselect[0].options == ["Max VERSTAPPEN", "Franco COLAPINTO"]


def test_dashboard_mostra_foto_e_substituto_na_classificacao(
    isolated_data_dir: Path,
) -> None:
    app = run_app(tables([session_row(11, "Race", "Race")]), isolated_data_dir)

    table = app.dataframe[0].value
    assert table["photo"][0] == "https://media.test/ver.png"
    assert table["photo"][1].startswith("data:image/svg+xml;base64,")
    assert list(table["position"]) == ["1", "–"]


def test_dashboard_treino_nao_mostra_evolucao_de_posicoes(
    isolated_data_dir: Path,
) -> None:
    app = run_app(
        tables([session_row(10, "Practice 1", "Practice")]), isolated_data_dir
    )

    assert not app.exception
    subheaders = [item.value for item in app.subheader]
    assert "Evolução das posições" not in subheaders
    assert "Estratégia de pneus" in subheaders


def test_dashboard_avisa_quando_nao_ha_sessoes_encerradas(
    isolated_data_dir: Path,
) -> None:
    data = tables([session_row(12, "Futura", "Race", end=FUTURE)])

    app = run_app(data, isolated_data_dir)

    assert not app.exception
    assert "sessões encerradas" in app.info[0].value


def test_dashboard_mostra_erro_de_leitura(isolated_data_dir: Path) -> None:
    (isolated_data_dir / "f1.duckdb").touch()

    with patch(
        "f1.extract.warehouse.read_table",
        side_effect=duckdb.IOException("arquivo travado"),
    ):
        app = AppTest.from_file(SCRIPT, default_timeout=60).run()

    assert not app.exception
    assert "arquivo travado" in app.error[0].value
