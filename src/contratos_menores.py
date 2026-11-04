from functools import partial
from pathlib import Path

import licitaciones
from descargas import download_files
from licitaciones import LicitacionesConfig, process_zip_files

CONFIG = LicitacionesConfig(
    base_url="https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_1143/",
    filename_pattern="contratosMenoresPerfilesContratantes_{period}.zip",
    start_year=2018,
    monthly_since=2025,
)

list_files = partial(licitaciones.list_files, config=CONFIG)


def main() -> None:
    yearmonth_from = "202601"
    yearmonth_to = "202701"
    output_dir = Path("data/contratos_menores")
    parsed_dir = Path("data/contratos_menores_parsed")
    overwrite = False

    files = list_files(yearmonth_from, yearmonth_to)
    print(f"{len(files)} files to check")

    downloaded = download_files(files, output_dir, overwrite=overwrite)
    print(f"{len(downloaded)}/{len(files)} files available in {output_dir}")

    output_files = process_zip_files(downloaded, parsed_dir, overwrite=overwrite)
    print(f"{len(output_files)} files parsed into {parsed_dir}")


if __name__ == "__main__":
    main()
