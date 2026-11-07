"""Geração do snapshot dos dados."""

import zipfile
from pathlib import Path


def write_snapshot(data_dir: Path, output: Path) -> int:
    """Compacta os arquivos Parquet em um zip, mantendo as pastas de partição.

    O banco DuckDB fica de fora porque suas views guardam caminhos absolutos desta
    máquina. Quem baixa o snapshot recria as views.

    Args:
        data_dir: Pasta raiz dos dados.
        output: Caminho do arquivo zip, substituído se já existir.

    Returns:
        Quantidade de arquivos compactados.

    Raises:
        ValueError: Se a pasta não tiver arquivos Parquet.
    """
    files = sorted(data_dir.rglob("*.parquet"))
    if not files:
        raise ValueError(f"Nenhum arquivo Parquet encontrado em {data_dir}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in files:
            archive.write(file, file.relative_to(data_dir))
    return len(files)
