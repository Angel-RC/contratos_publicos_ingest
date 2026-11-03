from pathlib import Path

import requests
from pydantic import BaseModel
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential
from tqdm import tqdm


class RemoteFile(BaseModel):
    name: str
    url: str
    year: int
    month: int | None = None


class FileNotAvailable(Exception):
    """The remote file does not exist yet (HTTP 404 or an HTML error page)."""


def download_files(
    files: list[RemoteFile],
    destination_dir: Path,
    *,
    overwrite: bool = False,
    session: requests.Session | None = None,
) -> list[Path]:
    session = session or requests.Session()
    destination_dir.mkdir(parents=True, exist_ok=True)

    downloaded = []
    for file in tqdm(files, desc="Downloading"):
        destination = destination_dir / file.name
        if destination.exists() and not overwrite:
            downloaded.append(destination)
            continue
        try:
            _download_one(session, file.url, destination)
        except FileNotAvailable:
            continue
        downloaded.append(destination)
    return downloaded


@retry(
    retry=retry_if_not_exception_type(FileNotAvailable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
def _download_one(session: requests.Session, url: str, destination: Path) -> None:
    response = session.get(url, timeout=600, stream=True)
    if response.status_code == 404 or "text/html" in response.headers.get("Content-Type", ""):
        raise FileNotAvailable(url)
    response.raise_for_status()
    with open(destination, "wb") as f:
        for chunk in response.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
