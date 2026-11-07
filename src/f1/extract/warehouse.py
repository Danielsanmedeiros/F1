"""Leitura das views do DuckDB."""

from pathlib import Path

import duckdb
import polars as pl


def build_select_sql(table: str, filters: dict[str, int]) -> tuple[str, list[int]]:
    """Gera a consulta de uma tabela com filtros de igualdade.

    Args:
        table: Nome da tabela, definido pelo código e nunca pelo usuário.
        filters: Colunas e valores a filtrar.

    Returns:
        Comando SQL com parâmetros e a lista de valores.
    """
    sql = f'SELECT * FROM "{table}"'
    if filters:
        conditions = " AND ".join(f'"{column}" = ?' for column in filters)
        sql = f"{sql} WHERE {conditions}"
    return sql, list(filters.values())


def read_table(db_path: Path, table: str, **filters: int) -> pl.DataFrame:
    """Lê uma tabela em uma conexão somente leitura, encerrada ao final.

    Manter a conexão aberta impediria o `f1-ingest` de recriar as views no Windows.
    As datas são retornadas em UTC, independentemente do fuso do computador.

    Args:
        db_path: Caminho do banco DuckDB.
        table: Nome da tabela.
        **filters: Colunas e valores a filtrar, como `session_key=9472`.

    Returns:
        Linhas encontradas.
    """
    sql, params = build_select_sql(table, filters)
    with duckdb.connect(str(db_path), read_only=True) as connection:
        connection.execute("SET TimeZone = 'UTC'")
        return connection.sql(sql, params=params).pl()
