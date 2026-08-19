from pathlib import Path

import requests
from pydantic import BaseModel
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential
from tqdm import tqdm

from parsing import parse_zip


class LicitacionesConfig(BaseModel):
    base_url: str = "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/"
    filename_pattern: str = "licitacionesPerfilesContratanteCompleto3_{period}.zip"
    start_year: int = 2012
    monthly_since: int = 2025


class RemoteFile(BaseModel):
    name: str
    url: str
    year: int
    month: int | None = None


def list_files(
    yearmonth_from: str,
    yearmonth_to: str,
    config: LicitacionesConfig | None = None,
) -> list[RemoteFile]:
    config = config or LicitacionesConfig()
    from_year, from_month = int(yearmonth_from[:4]), int(yearmonth_from[4:6])
    to_year, to_month = int(yearmonth_to[:4]), int(yearmonth_to[4:6])
    from_year = max(from_year, config.start_year)

    files = []
    for year in range(from_year, to_year + 1):
        if year >= config.monthly_since:
            month_start = from_month if year == from_year else 1
            month_end = to_month if year == to_year else 12
            for month in range(month_start, month_end + 1):
                files.append(_monthly_file(year, month, config))
        else:
            files.append(_annual_file(year, config))
    return files


def _annual_file(year: int, config: LicitacionesConfig) -> RemoteFile:
    name = config.filename_pattern.format(period=str(year))
    return RemoteFile(name=name, url=config.base_url + name, year=year, month=None)


def _monthly_file(year: int, month: int, config: LicitacionesConfig) -> RemoteFile:
    period = f"{year}{month:02d}"
    name = config.filename_pattern.format(period=period)
    return RemoteFile(name=name, url=config.base_url + name, year=year, month=month)


class FileNotAvailable(Exception):
    """The remote file does not exist yet (HTTP 404)."""


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
    if response.status_code == 404:
        raise FileNotAvailable(url)
    response.raise_for_status()
    with open(destination, "wb") as f:
        for chunk in response.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)


def process_zip_files(
    zip_paths: list[Path],
    output_dir: Path,
    *,
    overwrite: bool = False,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    output_paths = []
    for zip_path in tqdm(zip_paths, desc="Parsing"):
        output_path = output_dir / f"{zip_path.stem}.jsonl"
        if output_path.exists() and not overwrite:
            output_paths.append(output_path)
            continue
        with open(output_path, "w", encoding="utf-8") as f:
            for record in parse_zip(zip_path):
                f.write(record.model_dump_json() + "\n")
        output_paths.append(output_path)
    return output_paths


def main() -> None:
    yearmonth_from = "202601"
    yearmonth_to = "202608"
    output_dir = Path("data/licitaciones")
    parsed_dir = Path("data/licitaciones_parsed")
    overwrite = False

    files = list_files(yearmonth_from, yearmonth_to)
    print(f"{len(files)} files to check")

    downloaded = download_files(files, output_dir, overwrite=overwrite)
    print(f"{len(downloaded)}/{len(files)} files available in {output_dir}")

    output_files = process_zip_files(downloaded, parsed_dir, overwrite=overwrite)
    print(f"{len(output_files)} files parsed into {parsed_dir}")


if __name__ == "__main__":
    main()
