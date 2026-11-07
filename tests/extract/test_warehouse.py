from pathlib import Path
from unittest.mock import MagicMock, patch

from f1.extract.warehouse import build_select_sql, read_table


def test_build_select_sql_sem_filtros() -> None:
    assert build_select_sql("laps", {}) == ('SELECT * FROM "laps"', [])


def test_build_select_sql_usa_parametros_nos_filtros() -> None:
    sql, params = build_select_sql("laps", {"session_key": 9472, "lap_number": 3})

    assert sql == ('SELECT * FROM "laps" WHERE "session_key" = ? AND "lap_number" = ?')
    assert params == [9472, 3]


def test_read_table_usa_conexao_somente_leitura_e_utc(tmp_path: Path) -> None:
    db_path = tmp_path / "f1.duckdb"

    with patch("f1.extract.warehouse.duckdb.connect") as connect:
        connection = MagicMock()
        connect.return_value.__enter__.return_value = connection
        result = read_table(db_path, "laps", session_key=9472)

    connect.assert_called_once_with(str(db_path), read_only=True)
    connection.execute.assert_called_once_with("SET TimeZone = 'UTC'")
    connection.sql.assert_called_once_with(
        'SELECT * FROM "laps" WHERE "session_key" = ?', params=[9472]
    )
    assert result is connection.sql.return_value.pl.return_value
