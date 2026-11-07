from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import duckdb
import polars as pl
import pytest

from f1.extract.client import ApiAccessError, ApiRequestError
from f1.pipelines.ingest import IngestReport, main, run_ingest
from f1.transform.schemas import SESSION_SCHEMAS

NOW = datetime(2024, 6, 1, tzinfo=UTC)
PAST = "2024-03-02T17:00:00+00:00"
FUTURE = "2024-12-01T17:00:00+00:00"


def meeting() -> dict[str, Any]:
    return {
        "meeting_key": 1,
        "year": 2024,
        "circuit_key": 1,
        "country_key": 1,
        "date_start": PAST,
        "date_end": PAST,
        "meeting_name": "GP",
        "meeting_official_name": "Grande Prêmio",
        "location": "Sakhir",
        "country_code": "BRN",
        "country_name": "Bahrain",
        "circuit_short_name": "Sakhir",
        "gmt_offset": "03:00:00",
    }


def session(key: int, date_end: str = PAST, cancelled: bool = False) -> dict[str, Any]:
    return {
        "session_key": key,
        "meeting_key": 1,
        "year": 2024,
        "circuit_key": 1,
        "country_key": 1,
        "date_start": date_end,
        "date_end": date_end,
        "session_name": "Race",
        "session_type": "Race",
        "location": "Sakhir",
        "country_code": "BRN",
        "country_name": "Bahrain",
        "circuit_short_name": "Sakhir",
        "gmt_offset": "03:00:00",
        "is_cancelled": cancelled,
    }


class FakeSource:
    def __init__(self, sessions: list[dict[str, Any]]) -> None:
        self.sessions = sessions
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.errors: dict[str, Exception] = {}
        self.records: dict[str, list[dict[str, Any]]] = {}

    def get(self, endpoint: str, **params: str | int) -> list[dict[str, Any]]:
        self.calls.append((endpoint, params))
        if endpoint in self.errors:
            raise self.errors[endpoint]
        if endpoint in self.records:
            return self.records[endpoint]
        if endpoint == "meetings":
            return [meeting()]
        if endpoint == "sessions":
            return self.sessions
        return []

    def session_keys_fetched(self, endpoint: str = "laps") -> list[Any]:
        return [p["session_key"] for name, p in self.calls if name == endpoint]


def ingest(source: FakeSource, tmp_path: Path, **kwargs: Any) -> IngestReport:
    with patch("f1.pipelines.ingest.refresh_views"):
        return run_ingest(
            source,
            tmp_path,
            tmp_path / "f1.duckdb",
            [2024],
            now=NOW,
            **kwargs,
        )


def test_run_ingest_grava_todas_as_particoes(tmp_path: Path) -> None:
    report = ingest(FakeSource([session(10)]), tmp_path)

    assert report.succeeded
    assert report.written == 2 + len(SESSION_SCHEMAS)
    assert pl.read_parquet(tmp_path / "meetings/year=2024/data.parquet").height == 1
    laps = tmp_path / "laps/year=2024/session_key=10/data.parquet"
    assert pl.read_parquet(laps).is_empty()


def test_run_ingest_ignora_sessoes_futuras_e_canceladas(tmp_path: Path) -> None:
    source = FakeSource(
        [session(10), session(11, date_end=FUTURE), session(12, cancelled=True)]
    )

    ingest(source, tmp_path)

    assert source.session_keys_fetched() == [10]


def test_run_ingest_ignora_particao_existente(tmp_path: Path) -> None:
    ingest(FakeSource([session(10)]), tmp_path)
    source = FakeSource([session(10), session(20)])

    report = ingest(source, tmp_path)

    assert source.session_keys_fetched() == [20]
    assert report.skipped == len(SESSION_SCHEMAS)
    assert report.written == 2 + len(SESSION_SCHEMAS)


def test_run_ingest_atualiza_calendario_em_toda_execucao(tmp_path: Path) -> None:
    ingest(FakeSource([session(10)]), tmp_path)

    ingest(FakeSource([session(10), session(20)]), tmp_path)

    sessions = pl.read_parquet(tmp_path / "sessions/year=2024/data.parquet")
    assert sessions["session_key"].to_list() == [10, 20]


def test_run_ingest_force_recarrega_particoes(tmp_path: Path) -> None:
    ingest(FakeSource([session(10)]), tmp_path)
    source = FakeSource([session(10)])

    report = ingest(source, tmp_path, force=True)

    assert source.session_keys_fetched() == [10]
    assert report.skipped == 0


def test_run_ingest_continua_apos_falha_parcial_e_retoma(tmp_path: Path) -> None:
    source = FakeSource([session(10)])
    source.errors["laps"] = ApiRequestError("HTTP 500")

    report = ingest(source, tmp_path)

    assert not report.succeeded
    assert len(report.failures) == 1
    assert "laps" in report.failures[0].path
    assert source.session_keys_fetched("weather") == [10]

    retry = FakeSource([session(10)])
    retry_report = ingest(retry, tmp_path)

    assert retry_report.succeeded
    assert retry.session_keys_fetched() == [10]
    assert retry.session_keys_fetched("weather") == []


def test_run_ingest_registra_erro_de_schema_como_falha(tmp_path: Path) -> None:
    source = FakeSource([session(10)])
    source.records["weather"] = [{"session_key": 10}]

    report = ingest(source, tmp_path)

    paths = [failure.path for failure in report.failures]
    assert any("weather" in path for path in paths)
    assert not (tmp_path / "weather/year=2024/session_key=10/data.parquet").exists()


def test_run_ingest_sem_calendario_nao_busca_sessoes(tmp_path: Path) -> None:
    source = FakeSource([session(10)])
    source.errors["sessions"] = ApiRequestError("HTTP 500")

    report = ingest(source, tmp_path)

    assert not report.succeeded
    assert source.session_keys_fetched() == []


def test_run_ingest_interrompe_quando_acesso_e_recusado(tmp_path: Path) -> None:
    source = FakeSource([session(10)])
    source.errors["drivers"] = ApiAccessError("Live F1 session in progress")

    report = ingest(source, tmp_path)

    assert report.aborted_reason == "Live F1 session in progress"
    assert not report.succeeded
    assert source.session_keys_fetched() == []


def test_run_ingest_registra_falha_ao_recriar_views(tmp_path: Path) -> None:
    with patch(
        "f1.pipelines.ingest.refresh_views", side_effect=duckdb.IOException("travado")
    ):
        report = run_ingest(
            FakeSource([]), tmp_path, tmp_path / "f1.duckdb", [2024], now=NOW
        )

    assert [failure.path for failure in report.failures] == ["views do DuckDB"]


@pytest.mark.parametrize(
    ("report", "code"),
    [
        (IngestReport(written=1), 0),
        (IngestReport(aborted_reason="bloqueada"), 1),
    ],
)
def test_main_retorna_codigo_de_saida(
    report: IngestReport,
    code: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("F1_DATA_DIR", str(tmp_path))
    with patch("f1.pipelines.ingest.run_ingest", return_value=report) as run:
        assert main(["--year", "2024", "--year", "2023", "--year", "2024"]) == code

    assert list(run.call_args.args[3]) == [2024, 2023]
    assert run.call_args.kwargs["force"] is False


def test_main_repassa_force(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("F1_DATA_DIR", str(tmp_path))
    with patch("f1.pipelines.ingest.run_ingest", return_value=IngestReport()) as run:
        main(["--year", "2024", "--force"])

    assert run.call_args.kwargs["force"] is True


@pytest.mark.parametrize(
    "argv",
    [[], ["--year", "2022"], ["--year", "abc"]],
    ids=["sem-ano", "antigo", "txt"],
)
def test_main_rejeita_ano_invalido(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(argv)

    assert exit_info.value.code == 2
