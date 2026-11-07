"""Escrita atômica de partições em Parquet."""

import os
from pathlib import Path

import polars as pl


def partition_path(data_dir: Path, table: str, **partitions: int) -> Path:
    """Monta o caminho do arquivo de uma partição.

    Args:
        data_dir: Pasta raiz dos dados.
        table: Nome da tabela.
        **partitions: Valores da partição, na ordem das pastas.

    Returns:
        Caminho no formato `tabela/coluna=valor/data.parquet`.
    """
    folders = [f"{name}={value}" for name, value in partitions.items()]
    return data_dir.joinpath(table, *folders, "data.parquet")


def write_partition(df: pl.DataFrame, path: Path) -> None:
    """Grava uma partição, substituindo o arquivo existente de uma só vez.

    O arquivo é escrito ao lado do destino e movido só ao final. Em caso de falha, a
    versão anterior permanece intacta.

    Args:
        df: Dados da partição.
        path: Caminho do arquivo final.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        df.write_parquet(temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
