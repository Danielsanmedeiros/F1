import io
import zipfile
from pathlib import Path

import httpx
import pytest

from f1.extract.snapshot import download_snapshot

URL = "https://example.test/f1-data.zip"


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_download_snapshot_segue_redirecionamento_e_descompacta(
    tmp_path: Path,
) -> None:
    content = zip_bytes({"laps/year=2024/data.parquet": b"dados"})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "example.test":
            return httpx.Response(302, headers={"Location": "https://cdn.test/f.zip"})
        return httpx.Response(200, content=content)

    target = tmp_path / "novo" / "data"
    download_snapshot(URL, target, httpx.MockTransport(handler))

    assert (target / "laps" / "year=2024" / "data.parquet").read_bytes() == b"dados"


def test_download_snapshot_falha_com_erro_http(tmp_path: Path) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(404))

    with pytest.raises(httpx.HTTPStatusError):
        download_snapshot(URL, tmp_path, transport)


def test_download_snapshot_rejeita_conteudo_que_nao_e_zip(tmp_path: Path) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=b"<html>"))

    with pytest.raises(zipfile.BadZipFile):
        download_snapshot(URL, tmp_path, transport)
