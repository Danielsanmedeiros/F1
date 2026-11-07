import io
import zipfile
from pathlib import Path

import duckdb
import httpx
import polars as pl
import pytest

from f1.pipelines.snapshot import ensure_data, main

URL = "https://example.test/f1-data.zip"


def snapshot_bytes(tmp_path: Path) -> bytes:
    source = tmp_path / "origem.parquet"
    pl.DataFrame({"lap_number": [1, 2]}).write_parquet(source)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.write(source, "laps/year=2024/session_key=1/data.parquet")
    return buffer.getvalue()


def test_ensure_data_baixa_e_cria_views_consultaveis(tmp_path: Path) -> None:
    content = snapshot_bytes(tmp_path)
    data_dir = tmp_path / "data"
    db_path = data_dir / "f1.duckdb"

    ensure_data(
        URL,
        data_dir,
        db_path,
        httpx.MockTransport(lambda _: httpx.Response(200, content=content)),
    )

    with duckdb.connect(str(db_path), read_only=True) as connection:
        rows = connection.sql("SELECT count(*), any_value(year) FROM laps").fetchall()
    assert rows == [(2, 2024)]


def test_ensure_data_nao_baixa_se_o_banco_existe(tmp_path: Path) -> None:
    db_path = tmp_path / "f1.duckdb"
    db_path.touch()

    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("não deveria baixar")

    ensure_data(URL, tmp_path, db_path, httpx.MockTransport(handler))


def test_ensure_data_nao_cria_banco_se_o_download_falhar(tmp_path: Path) -> None:
    db_path = tmp_path / "f1.duckdb"

    with pytest.raises(httpx.HTTPStatusError):
        ensure_data(
            URL,
            tmp_path,
            db_path,
            httpx.MockTransport(lambda _: httpx.Response(500)),
        )

    assert not db_path.exists()


def test_main_gera_o_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = tmp_path / "data"
    (data_dir / "laps").mkdir(parents=True)
    (data_dir / "laps" / "data.parquet").write_bytes(b"dados")
    monkeypatch.setenv("F1_DATA_DIR", str(data_dir))
    output = tmp_path / "f1-data.zip"

    assert main(["--output", str(output)]) == 0
    assert output.exists()


def test_main_falha_sem_dados(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("F1_DATA_DIR", str(tmp_path))

    assert main(["--output", str(tmp_path / "f1-data.zip")]) == 1
