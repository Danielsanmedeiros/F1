from pathlib import Path
from unittest.mock import MagicMock, patch

from f1.load.duckdb import build_view_sql, refresh_views


def test_build_view_sql_usa_caminho_absoluto_e_union_by_name(tmp_path: Path) -> None:
    sql = build_view_sql("laps", tmp_path)

    assert sql.startswith(
        'CREATE OR REPLACE VIEW "laps" AS SELECT * FROM read_parquet('
    )
    assert f"{tmp_path.resolve().as_posix()}/laps/**/*.parquet" in sql
    assert "union_by_name=true" in sql
    assert "hive_partitioning=true" in sql


def test_build_view_sql_escapa_aspas_no_caminho(tmp_path: Path) -> None:
    sql = build_view_sql("laps", tmp_path / "d'ados")

    assert "d''ados" in sql


def test_refresh_views_cria_com_arquivos_e_remove_sem_arquivos(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    laps = data_dir / "laps" / "year=2024"
    laps.mkdir(parents=True)
    (laps / "data.parquet").touch()

    with patch("f1.load.duckdb.duckdb.connect") as connect:
        connection = MagicMock()
        connect.return_value.__enter__.return_value = connection
        refresh_views(data_dir / "f1.duckdb", data_dir, ["laps", "weather"])

    connect.assert_called_once_with(str(data_dir / "f1.duckdb"))
    executed = [call.args[0] for call in connection.execute.call_args_list]
    assert executed == [
        build_view_sql("laps", data_dir),
        'DROP VIEW IF EXISTS "weather"',
    ]
