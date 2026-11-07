"""Views do DuckDB sobre os arquivos Parquet."""

from collections.abc import Iterable
from pathlib import Path

import duckdb


def build_view_sql(table: str, data_dir: Path) -> str:
    """Gera o SQL que cria a view de uma tabela.

    Args:
        table: Nome da tabela.
        data_dir: Pasta raiz dos dados.

    Returns:
        Comando `CREATE OR REPLACE VIEW` com caminho absoluto. As colunas das pastas
        de partição, como `year`, ficam disponíveis na view.
    """
    pattern = (data_dir.resolve() / table / "**" / "*.parquet").as_posix()
    escaped = pattern.replace("'", "''")
    return (
        f'CREATE OR REPLACE VIEW "{table}" AS SELECT * FROM '
        f"read_parquet('{escaped}', union_by_name=true, hive_partitioning=true)"
    )


def refresh_views(db_path: Path, data_dir: Path, tables: Iterable[str]) -> None:
    """Recria as views no banco, removendo as de tabelas sem arquivos.

    Args:
        db_path: Caminho do arquivo do banco.
        data_dir: Pasta raiz dos dados.
        tables: Nomes das tabelas.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as connection:
        for table in tables:
            if any((data_dir / table).rglob("*.parquet")):
                connection.execute(build_view_sql(table, data_dir))
            else:
                connection.execute(f'DROP VIEW IF EXISTS "{table}"')
