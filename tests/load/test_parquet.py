from pathlib import Path

import polars as pl
import pytest

from f1.load.parquet import partition_path, write_partition


def test_partition_path_segue_a_ordem_das_pastas(tmp_path: Path) -> None:
    path = partition_path(tmp_path, "laps", year=2024, session_key=9165)

    assert path == tmp_path / "laps" / "year=2024" / "session_key=9165" / "data.parquet"


def test_write_partition_cria_pastas_e_grava(tmp_path: Path) -> None:
    path = tmp_path / "laps" / "year=2024" / "data.parquet"
    df = pl.DataFrame({"a": [1, 2]})

    write_partition(df, path)

    assert pl.read_parquet(path).equals(df)
    assert list(path.parent.iterdir()) == [path]


def test_write_partition_substitui_sem_acumular_linhas(tmp_path: Path) -> None:
    path = tmp_path / "data.parquet"

    write_partition(pl.DataFrame({"a": [1, 2]}), path)
    write_partition(pl.DataFrame({"a": [3]}), path)

    assert pl.read_parquet(path)["a"].to_list() == [3]


def test_write_partition_grava_df_vazio_com_schema(tmp_path: Path) -> None:
    path = tmp_path / "data.parquet"
    schema = {"a": pl.Int64, "s": pl.List(pl.Int64)}

    write_partition(pl.DataFrame(schema=schema), path)

    written = pl.read_parquet(path)
    assert written.is_empty()
    assert dict(written.schema) == schema


def test_write_partition_preserva_arquivo_antigo_em_caso_de_falha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "data.parquet"
    write_partition(pl.DataFrame({"a": [1]}), path)

    def fail(*_: object) -> None:
        raise OSError("disco cheio")

    monkeypatch.setattr("f1.load.parquet.os.replace", fail)

    with pytest.raises(OSError, match="disco cheio"):
        write_partition(pl.DataFrame({"a": [2]}), path)

    assert pl.read_parquet(path)["a"].to_list() == [1]
    assert list(tmp_path.iterdir()) == [path]
