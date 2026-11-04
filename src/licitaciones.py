from pathlib import Path

from pydantic import BaseModel
from tqdm import tqdm

from descargas import RemoteFile, download_files
from parsing import parse_zip


class FeedConfig(BaseModel):
    name: str
    base_url: str
    filename_pattern: str
    start_year: int
    monthly_since: int = 2025


LICITACIONES = FeedConfig(
    name="licitaciones",
    base_url="https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/",
    filename_pattern="licitacionesPerfilesContratanteCompleto3_{period}.zip",
    start_year=2012,
)

CONTRATOS_MENORES = FeedConfig(
    name="contratos_menores",
    base_url="https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_1143/",
    filename_pattern="contratosMenoresPerfilesContratantes_{period}.zip",
    start_year=2018,
)


def list_files(yearmonth_from: str, yearmonth_to: str, config: FeedConfig) -> list[RemoteFile]:
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


def _annual_file(year: int, config: FeedConfig) -> RemoteFile:
    name = config.filename_pattern.format(period=str(year))
    return RemoteFile(name=name, url=config.base_url + name, year=year, month=None)


def _monthly_file(year: int, month: int, config: FeedConfig) -> RemoteFile:
    period = f"{year}{month:02d}"
    name = config.filename_pattern.format(period=period)
    return RemoteFile(name=name, url=config.base_url + name, year=year, month=month)


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
        tmp_path = output_path.with_suffix(".jsonl.tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                for record in parse_zip(zip_path):
                    f.write(record.model_dump_json() + "\n")
        except BaseException:
            tmp_path.unlink()
            raise
        tmp_path.replace(output_path)
        output_paths.append(output_path)
    return output_paths


def main() -> None:
    yearmonth_from = "202601"
    yearmonth_to = "202701"
    overwrite = False

    for config in [LICITACIONES, CONTRATOS_MENORES]:
        output_dir = Path("data") / config.name
        parsed_dir = Path("data") / f"{config.name}_parsed"

        files = list_files(yearmonth_from, yearmonth_to, config)
        print(f"[{config.name}] {len(files)} files to check")

        downloaded = download_files(files, output_dir, overwrite=overwrite)
        print(f"[{config.name}] {len(downloaded)}/{len(files)} files available in {output_dir}")

        output_files = process_zip_files(downloaded, parsed_dir, overwrite=overwrite)
        print(f"[{config.name}] {len(output_files)} files parsed into {parsed_dir}")


if __name__ == "__main__":
    main()
