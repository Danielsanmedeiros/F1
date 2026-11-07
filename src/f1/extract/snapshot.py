"""Download do snapshot dos dados."""

import io
import zipfile
from pathlib import Path

import httpx

DOWNLOAD_TIMEOUT_SECONDS = 60.0


def download_snapshot(
    url: str, target_dir: Path, transport: httpx.BaseTransport | None = None
) -> None:
    """Baixa um snapshot e descompacta os arquivos em uma pasta.

    Args:
        url: Endereço do arquivo zip. Redirecionamentos são seguidos, como os dos
            anexos de releases do GitHub.
        target_dir: Pasta de destino, criada se não existir.
        transport: Transporte HTTP alternativo, usado nos testes.

    Raises:
        httpx.HTTPError: Se o download falhar.
        zipfile.BadZipFile: Se o conteúdo baixado não for um zip válido.
    """
    with httpx.Client(
        follow_redirects=True, timeout=DOWNLOAD_TIMEOUT_SECONDS, transport=transport
    ) as client:
        response = client.get(url)
        response.raise_for_status()

    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        archive.extractall(target_dir)
