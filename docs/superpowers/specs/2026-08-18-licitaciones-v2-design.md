# Diseño: v2 del pipeline de licitaciones nacionales (PLACSP)

## Contexto

El proyecto ya contiene una v2 parcial (`src/contratos_publicos_ingest/`) que reescribe
el script original `licitaciones-espana/nacional/licitaciones.py` como pipeline dlt:
descarga los ZIP en memoria (sin tocar disco), parsea las entradas ATOM/CODICE igual que
el original, y carga a DuckDB con `write_disposition="merge"` sobre `id`.

Esta v2 solo cubre el conjunto **`licitaciones`** (sindicacion_643) de los 5 que soporta
el script original — decisión de alcance explícita, ver "Fuera de alcance". El resto del
código existente (parsing, descarga, generación de periodos) se mantiene como base y se
adapta a las tres librerías que exige `CLAUDE.md` y que la v2 actual no usa: `pydantic`,
`hydra-core` (vía `OmegaConf`, sin `hydra.main`) y `tenacity`. Además se añade
incrementalidad para no volver a descargar periodos ya cargados en cada ejecución.

## Alcance

- Un único conjunto de datos: `licitaciones` (sindicacion_643, licitaciones excluyendo
  contratos menores).
- Los otros 4 conjuntos del script original (agregación, menores, encargos, consultas)
  quedan fuera de esta v2.

## Configuración: OmegaConf, sin `hydra.main`

Nuevo fichero `conf/config.yaml`:

```yaml
anos:
  inicio: 2012
  fin: 2026

pipeline:
  name: contratos_publicos_ingest
  destination: duckdb
  dataset_name: placsp
```

`pipeline.py` carga la configuración con `OmegaConf.load("conf/config.yaml")` y usa sus
valores directamente (`cfg.anos.inicio`, `cfg.anos.fin`, `cfg.pipeline.name`, etc.). No
hay `argparse`, no hay CLI, no hay decorador `@hydra.main`: para cambiar el rango de años
u otros parámetros de ejecución se edita el yaml. `main()` deja de aceptar argumentos.

Los mapeos de dominio que ya existen en `settings.py` (namespaces XML, `TIPOS_CONTRATO`,
`ESTADOS`, `PROCEDIMIENTOS`, `BASE_URL`, `FILE_PATTERN`) se quedan como constantes de
Python tal cual — son parte del esquema CODICE/ATOM, no configuración de despliegue, y no
se mueven a `conf/config.yaml`.

## Contrato de datos: pydantic

`parsing.py` define un modelo `Licitacion(BaseModel)` con los mismos ~40 campos que hoy
devuelve `parse_entry` como dict (`id`, `expediente`, `objeto`, `organo_contratante`,
`nif_organo`, `dir3_organo`, `id_plataforma`, `ciudad_organo`, `dependencia`,
`tipo_contrato_code`, `tipo_contrato`, `subtipo_code`, `procedimiento_code`,
`procedimiento`, `estado_code`, `estado`, `valor_estimado_contrato`, `importe_sin_iva`,
`importe_con_iva`, `importe_adjudicacion`, `importe_adj_con_iva`, `adjudicatario`,
`nif_adjudicatario`, `num_ofertas`, `es_pyme`, `cpv_principal`, `cpvs`, `ubicacion`,
`nuts`, `duracion`, `duracion_unidad`, `financiacion_ue`, `urgencia`, `fecha_limite`,
`hora_limite`, `fecha_adjudicacion`, `fecha_publicacion`, `fecha_updated`, `url`).

- `id` es obligatorio (`str`); si una entrada no trae `atom:id`, `parse_entry` devuelve
  `None` y se descarta (igual que ya hace hoy cuando falta `ContractFolderStatus`).
- El resto de campos son opcionales, tipados según su naturaleza actual (`str | None`,
  `float | None`, `int | None`, `bool | None`). Las fechas se mantienen como `str | None`
  (formato ISO tal cual viene del XML); dlt/DuckDB las tipa en destino, no hace falta
  parsear a `datetime` en Python.
- `parse_entry` devuelve `Licitacion | None` en vez de `dict | None`.
- `sources.py` hace yield de instancias `Licitacion` directamente; dlt las acepta de
  forma nativa (valida y usa el modelo para inferir el esquema de la tabla).

## Descarga y reintentos: tenacity

En `sources.py`, la función de descarga usa `@retry` de tenacity en vez del bucle manual
con `time.sleep(2**intento)`:

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1),
    retry=retry_if_exception_type(requests.RequestException),
)
def _fetch(session, url) -> bytes: ...
```

El 404 (periodo aún no publicado, p.ej. un mes futuro) no se reintenta: se captura por
separado (comprobando `response.status_code == 404` antes de que tenacity intervenga, o
excluyéndolo de la condición de retry) y la función que envuelve la descarga devuelve
`None` para saltar ese periodo sin más reintentos.

## Incrementalidad: watermark en el state de dlt

dlt no tiene ninguna noción de "este periodo ya se cargó, no lo descargues otra vez": el
`write_disposition="merge"` solo deduplica en el destino (DuckDB), después de que el
recurso ya ha vuelto a descargar y parsear el ZIP entero desde la red. Sin más cambios,
cada ejecución reprocesa siempre el rango de años completo.

Para evitarlo, `licitaciones_nacional` usa `dlt.current.resource_state()` para guardar un
watermark: el último periodo **cerrado** cargado con éxito.

- Un periodo es "abierto" si es el año o mes en curso (puede seguir recibiendo altas);
  cualquier otro periodo es "cerrado" y, una vez publicado, no cambia — misma asunción
  que ya hacía la caché en disco del script original.
- El watermark se guarda y compara como tupla `(ano, mes o 0)`, no como `periodo_str`:
  la comparación léxicográfica de strings entre periodos anuales (`"2024"`) y mensuales
  (`"202501"`) no es un orden robusto, aunque coincida por casualidad en la transición de
  2024 a 2025. La tupla ordena correctamente sin depender de la longitud del string.
- Al recorrer `periodos_en_rango(ano_inicio, ano_fin)`, se salta cualquier periodo
  cerrado cuya tupla `(ano, mes o 0)` sea ≤ al watermark almacenado.
- El periodo abierto nunca se salta: se descarga y reprocesa siempre.
- Al terminar de descargar y hacer yield con éxito de un periodo cerrado posterior al
  watermark, se actualiza el watermark a ese periodo.
- dlt confirma los cambios de state en el mismo commit que los datos al final de un
  `pipeline.run()` exitoso: si la ejecución falla a mitad, el watermark no avanza sobre
  periodos que no llegaron a cargarse.

## Testing

- `parse_entry` contra una fixture `.atom` de ejemplo (con y sin resultado de
  adjudicación), verificando el modelo `Licitacion` resultante.
- `periodos_en_rango`: caso anual (años < `MONTHLY_SINCE_YEAR`), caso mensual, límite del
  mes en curso cuando `ano == hoy.year`.
- Retry de descarga: mock de `requests` que falla N veces antes de responder 200, y caso
  404 que no reintenta.
- Watermark: dado un state previo, verificar qué periodos se saltan y cuáles no.

## Fuera de alcance

- Los conjuntos `agregacion`, `menores`, `encargos` y `consultas` del script original.
- CLI / `argparse` / `hydra.main`: la configuración de ejecución se edita en
  `conf/config.yaml`.
- Exportación a CSV/Parquet (el destino es DuckDB vía dlt).
- Caché de ficheros ZIP en disco (se mantiene la descarga en memoria de la v2 actual).
