# contratos-publicos-ingest

Ingesta con [dlt](https://dlthub.com) de las licitaciones públicas a nivel nacional
publicadas por la Plataforma de Contratación del Sector Público (PLACSP), en su
conjunto `sindicacion_643` (licitaciones excluyendo contratos menores).

Es la v2 del scraper nacional de [licitaciones-espana](../licitaciones-espana), reescrito
como pipeline dlt: descarga los ZIP/ATOM oficiales en memoria, los parsea a registros
planos y los carga en DuckDB con deduplicación automática por `id`.

## Uso

```bash
uv run contratos-publicos-ingest --anos 2020-2026
```

`--anos`: rango de años a ingerir, formato `YYYY-YYYY` (por defecto, el año actual).

Los datos quedan en un fichero DuckDB (`contratos_publicos_ingest.duckdb`), en el dataset
`placsp`, tabla `licitaciones`. Para explorarlos:

```bash
uv run python -c "import duckdb; print(duckdb.sql(\"select count(*) from placsp.licitaciones\"))"
```

## Cómo funciona

- Cada ZIP se descarga en memoria (`requests` + `zipfile.ZipFile` sobre un `BytesIO`), se
  parsea y se descarta: no se persiste ningún fichero en disco.
- La carga usa `write_disposition="merge"` con `id` como clave primaria, así que
  re-ejecutar el pipeline sobre el mismo rango de años es seguro y no genera duplicados
  (aunque sí vuelve a descargar y reprocesar todo, al no haber caché en disco).
- A partir de 2025 la plataforma publica un ZIP por mes en vez de uno por año; esto se
  gestiona automáticamente.

## Estructura

- `settings.py` — configuración estática (URLs, namespaces XML, tablas de mapeo).
- `parsing.py` — parsing de las entradas ATOM/CODICE (en memoria) a diccionarios planos.
- `sources.py` — recurso dlt: generación de periodos, descarga y extracción en memoria.
- `pipeline.py` — CLI y orquestación del `dlt.pipeline`.
