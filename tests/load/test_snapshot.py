import zipfile
from pathlib import Path

import pytest

from f1.load.snapshot import write_snapshot


def test_write_snapshot_compacta_parquet_e_ignora_o_banco(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    partition = data_dir / "laps" / "year=2024"
    partition.mkdir(parents=True)
    (partition / "data.parquet").write_bytes(b"dados")
    (data_dir / "f1.duckdb").write_bytes(b"banco")
    output = tmp_path / "dist" / "f1-data.zip"

    count = write_snapshot(data_dir, output)

    assert count == 1
    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == ["laps/year=2024/data.parquet"]


def test_write_snapshot_rejeita_pasta_sem_dados(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Nenhum arquivo Parquet"):
        write_snapshot(tmp_path, tmp_path / "f1-data.zip")
