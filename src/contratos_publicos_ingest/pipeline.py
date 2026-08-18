"""CLI y orquestación del pipeline dlt de licitaciones nacionales."""

from __future__ import annotations

import argparse
from datetime import date

import dlt

from .sources import placsp_source


def _parse_rango_anos(valor: str) -> tuple[int, int]:
    partes = valor.split("-")
    ano_inicio = int(partes[0])
    ano_fin = int(partes[1]) if len(partes) > 1 else ano_inicio
    return ano_inicio, ano_fin


def build_pipeline() -> dlt.Pipeline:
    return dlt.pipeline(
        pipeline_name="contratos_publicos_ingest",
        destination="duckdb",
        dataset_name="placsp",
    )


def run(ano_inicio: int, ano_fin: int) -> None:
    pipeline = build_pipeline()
    source = placsp_source(ano_inicio=ano_inicio, ano_fin=ano_fin)
    info = pipeline.run(source)
    print(info)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Ingesta de licitaciones nacionales (PLACSP) con dlt hacia DuckDB."
    )
    parser.add_argument(
        "--anos",
        type=str,
        default=str(date.today().year),
        help="Rango de años a ingerir, ej. 2020-2026 (por defecto: año actual).",
    )
    args = parser.parse_args(argv)

    ano_inicio, ano_fin = _parse_rango_anos(args.anos)
    run(ano_inicio, ano_fin)


if __name__ == "__main__":
    main()
