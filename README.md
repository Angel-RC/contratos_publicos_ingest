# contratos-publicos-ingest

Descarga y parseo de los datos abiertos de la Plataforma de Contratación del Sector
Público (PLACSP) a ficheros JSONL planos, más unas tablas maestras que limpian y
unifican los nombres de órganos de contratación y adjudicatarios.

Conjuntos cubiertos:

- **Licitaciones** (`sindicacion_643`, excluye contratos menores): desde 2012.
- **Contratos menores** (`sindicacion_1143`): desde 2018.

La plataforma publica un ZIP por año hasta 2024 y uno por mes desde 2025; se gestiona
automáticamente.

## Uso

```bash
uv sync
uv run python src/licitaciones.py
```

El script ingesta primero las licitaciones y después los contratos menores: es la misma
lógica, solo cambia la configuración (`LICITACIONES` / `CONTRATOS_MENORES`). No hay CLI:
el rango de fechas (`yearmonth_from` / `yearmonth_to`, formato `YYYYMM`) y `overwrite`
se editan directamente en `main()`.

Para cada conjunto:

1. Descarga los ZIP que falten (con reintentos vía `tenacity`; los ya descargados se
   saltan salvo `overwrite=True`).
2. Parsea cada ZIP a un `.jsonl` con el mismo nombre, un registro por licitación. Los
   ZIP ya parseados se saltan, así que re-ejecutar mes a mes solo procesa lo nuevo.

Tests:

```bash
uv run pytest
```

## Estructura

```
src/
  descargas.py          descarga de ficheros remotos (RemoteFile, download_files)
  parsing.py            parsing CODICE/Atom -> TenderRecord (pydantic)
  licitaciones.py       configuración de cada conjunto, listado de ZIP y main()
sql/
  organismo_key.sql             macros compartidas (normalizar_clave, organismo_key...)
  generar_organos.sql           genera data/masters/organos.jsonl
  generar_adjudicatarios.sql    genera data/masters/adjudicatarios.jsonl
data/
  licitaciones/ , contratos_menores/                ZIP descargados (no versionados)
  licitaciones_parsed/ , contratos_menores_parsed/  JSONL parseados (no versionados)
  masters/                                          tablas maestras
```

## Tablas maestras

Tablas de correspondencia entre los nombres tal como aparecen en los datos y un nombre
limpio. Se generan con DuckDB sobre los JSONL parseados:

```bash
duckdb -c ".read sql/organismo_key.sql" -c ".read sql/generar_organos.sql"
duckdb -c ".read sql/organismo_key.sql" -c ".read sql/generar_adjudicatarios.sql"
```

**Solo añaden filas nuevas**: las que ya existen en el fichero (incluidas las
correcciones hechas a mano) nunca se recalculan. Por eso, si se cambia una regla de
limpieza y se quiere aplicar a todo, hay que vaciar el fichero y regenerarlo (perdiendo
las correcciones manuales). El fichero debe existir antes de la primera ejecución
(`touch data/masters/adjudicatarios.jsonl`).

Para cruzarlas con los datos, usar `normalizar_clave()` en ambos lados: las variantes
que solo difieren en mayúsculas, tildes o espacios comparten una única fila.

Ambas tienen una columna `fiabilidad` (`fiable` / `revision`) que marca las filas cuyo
nombre limpio conviene revisar a mano.

### `organos.jsonl`

Una fila por `(organo_nif, organo_nombre, organo_ciudad, dependencia, organo_tipo_code)`,
solo de licitaciones. El NIF no basta como clave: muchas entidades distintas comparten
NIF con su matriz (aeropuertos de AENA, Consejerías de una comunidad...). La agrupación
combina NIF, nombre y `dependencia` según reglas validadas por categoría; ver los
comentarios de `sql/organismo_key.sql` y `sql/generar_organos.sql`. Añade también
`comunidad_autonoma`, `provincia` y `municipio` extraídos de `dependencia`.

### `adjudicatarios.jsonl`

Una fila por `(nif_adjudicatario, adjudicatario)`, de licitaciones y contratos menores.
Aquí el NIF sí es la identidad jurídica, así que se agrupa por NIF normalizado y el
nombre limpio (`adjudicatario_limpio`, en mayúsculas y con la forma societaria
unificada: "SAU", "S.A.U," -> ", S.A.U.") es la variante más frecuente del grupo.
Excepciones:

- `nif_agrupable = false`: NIFs anonimizados (`***2317**`), identificadores numéricos,
  de relleno (`00000000X`, `A00000000`) o basura (`N/A`). Se agrupan solo por nombre.
- `es_ute = true`: Uniones Temporales de Empresas. Cuando una UTE aparece con el NIF de
  una de sus socias, se mantiene separada de la empresa (se agrupa por NIF + nombre).

`fiabilidad = 'revision'` marca nombres que no se parecen al canónico de su NIF: siglas,
nombres comerciales, cambios de razón social (Cepsa -> Moeve) o NIF mal asignado.
Una corrección manual de `adjudicatario_limpio` se hereda en las variantes nuevas del
mismo grupo que aparezcan en ejecuciones posteriores.
