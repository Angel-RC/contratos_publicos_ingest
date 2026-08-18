# v2 Pipeline de Licitaciones Nacionales — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adapt the existing dlt pipeline for PLACSP `licitaciones` (sindicacion_643) to use pydantic, OmegaConf-based configuration, and tenacity, and add a state-based watermark so reruns skip already-loaded periods.

**Architecture:** Four independent, sequential changes to the existing `src/contratos_publicos_ingest/` package: a pydantic `Licitacion` model replacing the current dict contract, an OmegaConf-loaded `conf/config.yaml` replacing `argparse`, tenacity-based retries replacing the manual retry loop, and a watermark stored in `dlt.current.resource_state()` to skip closed periods already loaded. No new conjuntos, no CLI, no disk cache.

**Tech Stack:** Python 3.14, dlt (duckdb destination), pydantic, OmegaConf, tenacity, requests, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-08-18-licitaciones-v2-design.md`

## Global Constraints

- Alcance: solo el conjunto `licitaciones` (sindicacion_643). No se tocan otros conjuntos.
- Sin `argparse`/CLI/`hydra.main`: la configuración de ejecución vive en `conf/config.yaml`, cargada con `OmegaConf.load`.
- `id` es obligatorio en `Licitacion`; si una entrada no trae `atom:id`, `parse_entry` devuelve `None` y se descarta.
- dlt consume instancias `Licitacion` directamente vía `yield` (no dicts).
- Un 404 al descargar un ZIP no se reintenta; cualquier otro error de red se reintenta hasta 3 intentos con backoff exponencial (tenacity) y luego se propaga.
- El watermark de periodos cargados se guarda y compara como tupla `(ano, mes o 0)`, nunca como el string `periodo_str`.
- `python >=3.14` (ya fijado en `pyproject.toml`); usa `uv add`/`uv add --dev` para nuevas dependencias, nunca edites `pyproject.toml`/`uv.lock` a mano para versiones.

---

## Task 1: Contrato de datos con pydantic

**Files:**
- Create: `src/contratos_publicos_ingest/models.py`
- Modify: `src/contratos_publicos_ingest/parsing.py`
- Modify: `src/contratos_publicos_ingest/sources.py` (type hints only, no behavior change in this task)
- Modify: `pyproject.toml` (via `uv add`)
- Test: `tests/test_parsing.py`

**Interfaces:**
- Produces: `Licitacion(BaseModel)` in `contratos_publicos_ingest.models` with fields `id: str` (required) and the following optional fields (all default `None`): `expediente, objeto, organo_contratante, nif_organo, dir3_organo, id_plataforma, ciudad_organo, dependencia, tipo_contrato_code, tipo_contrato, subtipo_code, procedimiento_code, procedimiento, estado_code, estado` (`str | None`); `valor_estimado_contrato, importe_sin_iva, importe_con_iva, importe_adjudicacion, importe_adj_con_iva` (`float | None`); `adjudicatario, nif_adjudicatario` (`str | None`); `num_ofertas` (`int | None`); `es_pyme` (`bool | None`); `cpv_principal, cpvs, ubicacion, nuts, duracion, duracion_unidad, financiacion_ue, urgencia, fecha_limite, hora_limite, fecha_adjudicacion, fecha_publicacion, fecha_updated, url` (`str | None`).
- Produces: `parsing.parse_entry(entry: ET.Element) -> Licitacion | None`.
- Produces: `parsing.iter_entries_from_atom_bytes(data: bytes) -> Iterator[Licitacion]`.

- [ ] **Step 1: Add dependencies**

```bash
uv add pydantic
uv add --dev pytest
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_parsing.py`:

```python
from contratos_publicos_ingest.models import Licitacion
from contratos_publicos_ingest.parsing import iter_entries_from_atom_bytes

FEED_CON_ADJUDICACION = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:cbc="urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2"
      xmlns:cac="urn:dgpe:names:draft:codice:schema:xsd:CommonAggregateComponents-2"
      xmlns:cbc-place-ext="urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonBasicComponents-2"
      xmlns:cac-place-ext="urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2">
  <entry>
    <id>https://contrataciondelsectorpublico.gob.es/wps/poc/expediente/12345</id>
    <link href="https://contrataciondelsectorpublico.gob.es/wps/poc/expediente/12345.atom"/>
    <updated>2026-01-15T10:00:00Z</updated>
    <cac-place-ext:ContractFolderStatus>
      <cbc:ContractFolderID>EXP-2026-001</cbc:ContractFolderID>
      <cbc-place-ext:ContractFolderStatusCode>ADJ</cbc-place-ext:ContractFolderStatusCode>
      <cac-place-ext:LocatedContractingParty>
        <cac:Party>
          <cac:PartyIdentification>
            <cbc:ID schemeName="NIF">Q1234567A</cbc:ID>
          </cac:PartyIdentification>
          <cac:PartyIdentification>
            <cbc:ID schemeName="DIR3">L01234567</cbc:ID>
          </cac:PartyIdentification>
          <cac:PartyName>
            <cbc:Name>Ayuntamiento de Prueba</cbc:Name>
          </cac:PartyName>
          <cac:PostalAddress>
            <cbc:CityName>Prueba</cbc:CityName>
          </cac:PostalAddress>
        </cac:Party>
      </cac-place-ext:LocatedContractingParty>
      <cac:ProcurementProject>
        <cbc:Name>Suministro de material de oficina</cbc:Name>
        <cbc:TypeCode>1</cbc:TypeCode>
        <cbc:SubTypeCode>1</cbc:SubTypeCode>
        <cac:BudgetAmount>
          <cbc:EstimatedOverallContractAmount>10000.00</cbc:EstimatedOverallContractAmount>
          <cbc:TotalAmount>12100.00</cbc:TotalAmount>
          <cbc:TaxExclusiveAmount>10000.00</cbc:TaxExclusiveAmount>
        </cac:BudgetAmount>
        <cac:RequiredCommodityClassification>
          <cbc:ItemClassificationCode>30192000</cbc:ItemClassificationCode>
        </cac:RequiredCommodityClassification>
        <cac:RealizedLocation>
          <cbc:CountrySubentity>Madrid</cbc:CountrySubentity>
          <cbc:CountrySubentityCode>ES300</cbc:CountrySubentityCode>
        </cac:RealizedLocation>
        <cac:PlannedPeriod>
          <cbc:DurationMeasure unitCode="MON">12</cbc:DurationMeasure>
        </cac:PlannedPeriod>
      </cac:ProcurementProject>
      <cac:TenderingProcess>
        <cbc:ProcedureCode>1</cbc:ProcedureCode>
        <cbc:UrgencyCode>1</cbc:UrgencyCode>
        <cac:TenderSubmissionDeadlinePeriod>
          <cbc:EndDate>2026-02-01</cbc:EndDate>
          <cbc:EndTime>14:00:00</cbc:EndTime>
        </cac:TenderSubmissionDeadlinePeriod>
      </cac:TenderingProcess>
      <cac:TenderingTerms>
        <cbc:FundingProgramCode>1</cbc:FundingProgramCode>
      </cac:TenderingTerms>
      <cac:TenderResult>
        <cac:WinningParty>
          <cac:PartyIdentification>
            <cbc:ID>B87654321</cbc:ID>
          </cac:PartyIdentification>
          <cac:PartyName>
            <cbc:Name>Suministros Prueba SL</cbc:Name>
          </cac:PartyName>
        </cac:WinningParty>
        <cac:AwardedTenderedProject>
          <cac:LegalMonetaryTotal>
            <cbc:TaxExclusiveAmount>9800.00</cbc:TaxExclusiveAmount>
            <cbc:PayableAmount>11858.00</cbc:PayableAmount>
          </cac:LegalMonetaryTotal>
        </cac:AwardedTenderedProject>
        <cbc:AwardDate>2026-01-10</cbc:AwardDate>
        <cbc:ReceivedTenderQuantity>3</cbc:ReceivedTenderQuantity>
        <cbc:SMEAwardedIndicator>true</cbc:SMEAwardedIndicator>
      </cac:TenderResult>
      <cac-place-ext:ValidNoticeInfo>
        <cac-place-ext:AdditionalPublicationDocumentReference>
          <cbc:IssueDate>2026-01-01</cbc:IssueDate>
        </cac-place-ext:AdditionalPublicationDocumentReference>
      </cac-place-ext:ValidNoticeInfo>
    </cac-place-ext:ContractFolderStatus>
  </entry>
</feed>
"""

FEED_SIN_ID = FEED_CON_ADJUDICACION.replace(
    "<id>https://contrataciondelsectorpublico.gob.es/wps/poc/expediente/12345</id>", ""
)


def test_parsea_entrada_con_adjudicacion_a_licitacion():
    entradas = list(iter_entries_from_atom_bytes(FEED_CON_ADJUDICACION.encode("utf-8")))

    assert len(entradas) == 1
    licitacion = entradas[0]
    assert isinstance(licitacion, Licitacion)
    assert licitacion.id == "https://contrataciondelsectorpublico.gob.es/wps/poc/expediente/12345"
    assert licitacion.expediente == "EXP-2026-001"
    assert licitacion.organo_contratante == "Ayuntamiento de Prueba"
    assert licitacion.nif_organo == "Q1234567A"
    assert licitacion.dir3_organo == "L01234567"
    assert licitacion.tipo_contrato == "Suministros"
    assert licitacion.estado == "Adjudicada"
    assert licitacion.procedimiento == "Abierto"
    assert licitacion.importe_sin_iva == 10000.00
    assert licitacion.cpv_principal == "30192000"
    assert licitacion.adjudicatario == "Suministros Prueba SL"
    assert licitacion.nif_adjudicatario == "B87654321"
    assert licitacion.importe_adjudicacion == 9800.00
    assert licitacion.num_ofertas == 3
    assert licitacion.es_pyme is True
    assert licitacion.fecha_publicacion == "2026-01-01"


def test_entrada_sin_id_se_descarta():
    entradas = list(iter_entries_from_atom_bytes(FEED_SIN_ID.encode("utf-8")))

    assert entradas == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_parsing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'contratos_publicos_ingest.models'` (or import error), since `models.py` and the `Licitacion` return type don't exist yet.

- [ ] **Step 4: Create `src/contratos_publicos_ingest/models.py`**

```python
"""Contrato de datos de una licitación parseada (PLACSP)."""

from __future__ import annotations

from pydantic import BaseModel


class Licitacion(BaseModel):
    id: str
    expediente: str | None = None
    objeto: str | None = None
    organo_contratante: str | None = None
    nif_organo: str | None = None
    dir3_organo: str | None = None
    id_plataforma: str | None = None
    ciudad_organo: str | None = None
    dependencia: str | None = None
    tipo_contrato_code: str | None = None
    tipo_contrato: str | None = None
    subtipo_code: str | None = None
    procedimiento_code: str | None = None
    procedimiento: str | None = None
    estado_code: str | None = None
    estado: str | None = None
    valor_estimado_contrato: float | None = None
    importe_sin_iva: float | None = None
    importe_con_iva: float | None = None
    importe_adjudicacion: float | None = None
    importe_adj_con_iva: float | None = None
    adjudicatario: str | None = None
    nif_adjudicatario: str | None = None
    num_ofertas: int | None = None
    es_pyme: bool | None = None
    cpv_principal: str | None = None
    cpvs: str | None = None
    ubicacion: str | None = None
    nuts: str | None = None
    duracion: str | None = None
    duracion_unidad: str | None = None
    financiacion_ue: str | None = None
    urgencia: str | None = None
    fecha_limite: str | None = None
    hora_limite: str | None = None
    fecha_adjudicacion: str | None = None
    fecha_publicacion: str | None = None
    fecha_updated: str | None = None
    url: str | None = None
```

- [ ] **Step 5: Update `src/contratos_publicos_ingest/parsing.py`**

Replace the import block:

```python
from typing import Any, Iterator

from .settings import ESTADOS, NS, PROCEDIMIENTOS, TIPOS_CONTRATO
```

with:

```python
from typing import Iterator

from .models import Licitacion
from .settings import ESTADOS, NS, PROCEDIMIENTOS, TIPOS_CONTRATO
```

Replace the function signature and the id check at the top of `parse_entry`:

```python
def parse_entry(entry: ET.Element) -> dict[str, Any] | None:
    """Convierte un <atom:entry> de licitación en un diccionario plano.

    Devuelve None si la entrada no trae el contenedor CODICE esperado o si
    el parsing falla, en vez de propagar la excepción y detener el pipeline.
    """
    try:
        id_lic = _safe_text(entry, "atom:id")
        link = entry.find("atom:link", NS)
        url = link.get("href") if link is not None else None

        status = entry.find("cac-place-ext:ContractFolderStatus", NS)
        if status is None:
            return None
```

with:

```python
def parse_entry(entry: ET.Element) -> Licitacion | None:
    """Convierte un <atom:entry> de licitación en una Licitacion.

    Devuelve None si la entrada no trae `atom:id`, no trae el contenedor
    CODICE esperado, o si el parsing falla, en vez de propagar la excepción
    y detener el pipeline.
    """
    try:
        id_lic = _safe_text(entry, "atom:id")
        if not id_lic:
            return None

        link = entry.find("atom:link", NS)
        url = link.get("href") if link is not None else None

        status = entry.find("cac-place-ext:ContractFolderStatus", NS)
        if status is None:
            return None
```

Replace the final `return {...}` dict literal (everything from `return {` through the closing `}` right before `except Exception:`) with:

```python
        data = {
            "id": id_lic,
            "expediente": expediente,
            "objeto": objeto,
            "organo_contratante": nombre_organo,
            "nif_organo": nif_organo,
            "dir3_organo": dir3_organo,
            "id_plataforma": id_plataforma,
            "ciudad_organo": ciudad_organo,
            "dependencia": dependencia,
            "tipo_contrato_code": tipo_code,
            "tipo_contrato": TIPOS_CONTRATO.get(tipo_code, tipo_code),
            "subtipo_code": subtipo_code,
            "procedimiento_code": procedimiento_code,
            "procedimiento": PROCEDIMIENTOS.get(procedimiento_code, procedimiento_code),
            "estado_code": estado_code,
            "estado": ESTADOS.get(estado_code, estado_code),
            "valor_estimado_contrato": valor_estimado_contrato,
            "importe_sin_iva": importe_sin_iva,
            "importe_con_iva": importe_con_iva,
            "importe_adjudicacion": importe_adjudicacion,
            "importe_adj_con_iva": importe_adj_con_iva,
            "adjudicatario": adjudicatario,
            "nif_adjudicatario": nif_adjudicatario,
            "num_ofertas": num_ofertas,
            "es_pyme": es_pyme,
            "cpv_principal": cpv_principal,
            "cpvs": cpvs_todos,
            "ubicacion": ubicacion,
            "nuts": nuts,
            "duracion": duracion,
            "duracion_unidad": duracion_unidad,
            "financiacion_ue": financiacion_ue,
            "urgencia": urgencia,
            "fecha_limite": fecha_limite,
            "hora_limite": hora_limite,
            "fecha_adjudicacion": fecha_adjudicacion,
            "fecha_publicacion": fecha_publicacion,
            "fecha_updated": fecha_updated,
            "url": url,
        }
        return Licitacion(**data)
```

Finally, update `iter_entries_from_atom_bytes`'s return type annotation from `Iterator[dict[str, Any]]` to `Iterator[Licitacion]` (the body is unchanged).

- [ ] **Step 6: Update `src/contratos_publicos_ingest/sources.py` type hints**

Replace:

```python
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterator

import dlt
import requests

from .parsing import iter_entries_from_atom_bytes
from .settings import BASE_URL, FILE_PATTERN, FIRST_YEAR, MONTHLY_SINCE_YEAR, USER_AGENT
```

with:

```python
from dataclasses import dataclass
from datetime import date
from typing import Iterator

import dlt
import requests

from .models import Licitacion
from .parsing import iter_entries_from_atom_bytes
from .settings import BASE_URL, FILE_PATTERN, FIRST_YEAR, MONTHLY_SINCE_YEAR, USER_AGENT
```

Replace the two `Iterator[dict[str, Any]]` return type annotations (on `_entries_from_zip_bytes` and `licitaciones_nacional`) with `Iterator[Licitacion]`.

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run pytest tests/test_parsing.py -v`
Expected: PASS (2 tests)

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock src/contratos_publicos_ingest/models.py src/contratos_publicos_ingest/parsing.py src/contratos_publicos_ingest/sources.py tests/test_parsing.py
git commit -m "Sustituye el dict de licitaciones por un modelo pydantic Licitacion"
```

---

## Task 2: Configuración con OmegaConf (sin hydra.main)

**Files:**
- Create: `conf/config.yaml`
- Modify: `src/contratos_publicos_ingest/pipeline.py`
- Modify: `pyproject.toml` (via `uv add`)
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `sources.placsp_source(ano_inicio: int, ano_fin: int)` (unchanged from current code).
- Produces: `pipeline.CONFIG_PATH: Path`, `pipeline.build_pipeline(cfg) -> dlt.Pipeline`, `pipeline.run(ano_inicio: int, ano_fin: int, cfg) -> None`, `pipeline.main() -> None` (no arguments — no CLI).

- [ ] **Step 1: Add dependency**

```bash
uv add omegaconf
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_pipeline.py`:

```python
from omegaconf import OmegaConf

from contratos_publicos_ingest import pipeline


def test_config_file_tiene_la_forma_esperada():
    cfg = OmegaConf.load(pipeline.CONFIG_PATH)

    assert isinstance(cfg.anos.inicio, int)
    assert isinstance(cfg.anos.fin, int)
    assert cfg.anos.inicio <= cfg.anos.fin
    assert cfg.pipeline.name
    assert cfg.pipeline.destination
    assert cfg.pipeline.dataset_name


def test_main_llama_a_run_con_los_valores_del_config(monkeypatch):
    llamadas = []

    def fake_run(ano_inicio, ano_fin, cfg):
        llamadas.append((ano_inicio, ano_fin, cfg))

    monkeypatch.setattr(pipeline, "run", fake_run)
    pipeline.main()

    assert len(llamadas) == 1
    ano_inicio, ano_fin, cfg = llamadas[0]
    esperado = OmegaConf.load(pipeline.CONFIG_PATH)
    assert ano_inicio == esperado.anos.inicio
    assert ano_fin == esperado.anos.fin
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: FAIL — `pipeline.CONFIG_PATH` doesn't exist yet (`AttributeError`), and `pipeline.main` currently takes an `argv` parameter tied to `argparse`, not zero-argument config loading.

- [ ] **Step 4: Create `conf/config.yaml`**

```yaml
anos:
  inicio: 2012
  fin: 2026

pipeline:
  name: contratos_publicos_ingest
  destination: duckdb
  dataset_name: placsp
```

- [ ] **Step 5: Rewrite `src/contratos_publicos_ingest/pipeline.py`**

Replace the entire file content with:

```python
"""CLI y orquestación del pipeline dlt de licitaciones nacionales."""

from __future__ import annotations

from pathlib import Path

import dlt
from omegaconf import OmegaConf

from .sources import placsp_source

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "conf" / "config.yaml"


def build_pipeline(cfg) -> dlt.Pipeline:
    return dlt.pipeline(
        pipeline_name=cfg.pipeline.name,
        destination=cfg.pipeline.destination,
        dataset_name=cfg.pipeline.dataset_name,
    )


def run(ano_inicio: int, ano_fin: int, cfg) -> None:
    pipeline = build_pipeline(cfg)
    source = placsp_source(ano_inicio=ano_inicio, ano_fin=ano_fin)
    info = pipeline.run(source)
    print(info)


def main() -> None:
    cfg = OmegaConf.load(CONFIG_PATH)
    run(cfg.anos.inicio, cfg.anos.fin, cfg)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Update the README usage section**

In `README.md`, replace the `## Uso` section (currently showing `uv run contratos-publicos-ingest --anos 2020-2026`) with:

```markdown
## Uso

```bash
uv run contratos-publicos-ingest
```

El rango de años a ingerir se configura en `conf/config.yaml` (`anos.inicio`, `anos.fin`),
no por línea de comandos.
```

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock conf/config.yaml src/contratos_publicos_ingest/pipeline.py tests/test_pipeline.py README.md
git commit -m "Sustituye argparse por configuración OmegaConf en conf/config.yaml"
```

---

## Task 3: Reintentos con tenacity

**Files:**
- Modify: `src/contratos_publicos_ingest/sources.py`
- Modify: `pyproject.toml` (via `uv add`)
- Test: `tests/test_sources.py`

**Interfaces:**
- Produces: `sources._descargar_zip(session: requests.Session, url: str) -> bytes | None` (drops the `max_reintentos` parameter — tenacity owns the retry count now).

- [ ] **Step 1: Add dependency**

```bash
uv add tenacity
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_sources.py`:

```python
import requests

from contratos_publicos_ingest.sources import _descargar_zip


class _FakeResponse:
    def __init__(self, status_code: int, content: bytes = b""):
        self.status_code = status_code
        self.content = content

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(response=self)


class _FlakySession:
    """Falla `fallos` veces con un error de conexión y luego responde."""

    def __init__(self, fallos: int, status_code: int = 200, content: bytes = b"ok"):
        self.fallos = fallos
        self.status_code = status_code
        self.content = content
        self.llamadas = 0

    def get(self, url: str, timeout: int) -> _FakeResponse:
        self.llamadas += 1
        if self.llamadas <= self.fallos:
            raise requests.exceptions.ConnectionError("fallo simulado")
        return _FakeResponse(self.status_code, self.content)


def test_descargar_zip_reintenta_y_recupera():
    session = _FlakySession(fallos=2)

    resultado = _descargar_zip(session, "https://example.test/archivo.zip")

    assert resultado == b"ok"
    assert session.llamadas == 3


def test_descargar_zip_no_reintenta_en_404():
    session = _FlakySession(fallos=0, status_code=404)

    resultado = _descargar_zip(session, "https://example.test/archivo.zip")

    assert resultado is None
    assert session.llamadas == 1


def test_descargar_zip_agota_reintentos_y_propaga():
    session = _FlakySession(fallos=5)

    try:
        _descargar_zip(session, "https://example.test/archivo.zip")
        raise AssertionError("se esperaba que propagase ConnectionError")
    except requests.exceptions.ConnectionError:
        pass

    assert session.llamadas == 3
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_sources.py -v`
Expected: FAIL — `_descargar_zip` currently loops with `max_reintentos` and swallows the exhausted-retry case by returning `None` instead of propagating, so `test_descargar_zip_agota_reintentos_y_propaga` fails (no exception raised, or wrong call count for the others due to `time.sleep(2**intento)` not being the tenacity backoff — the call counts still happen to match, but the exhaustion behavior differs).

- [ ] **Step 4: Replace the retry logic in `src/contratos_publicos_ingest/sources.py`**

Add to the imports:

```python
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential
```

Replace:

```python
def _descargar_zip(
    session: requests.Session, url: str, max_reintentos: int = 3
) -> bytes | None:
    """Descarga un ZIP directamente a memoria. Devuelve None si no existe (404)."""
    for intento in range(max_reintentos):
        try:
            response = session.get(url, timeout=600)
            response.raise_for_status()
            return response.content
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None
            time.sleep(2**intento)
        except requests.exceptions.RequestException:
            time.sleep(2**intento)

    return None
```

with:

```python
def _es_reintentable(exc: BaseException) -> bool:
    if isinstance(exc, requests.exceptions.HTTPError):
        return exc.response is None or exc.response.status_code != 404
    return isinstance(exc, requests.exceptions.RequestException)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1),
    retry=retry_if_exception(_es_reintentable),
    reraise=True,
)
def _fetch(session: requests.Session, url: str) -> bytes:
    response = session.get(url, timeout=600)
    response.raise_for_status()
    return response.content


def _descargar_zip(session: requests.Session, url: str) -> bytes | None:
    """Descarga un ZIP directamente a memoria. Devuelve None si no existe (404)."""
    try:
        return _fetch(session, url)
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return None
        raise
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_sources.py -v`
Expected: PASS (3 tests). Note: this run takes a few real seconds due to `wait_exponential` backoff between simulated failures — that's expected, not a hang.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/contratos_publicos_ingest/sources.py tests/test_sources.py
git commit -m "Sustituye el retry manual de descarga por tenacity"
```

---

## Task 4: Watermark de periodos ya cargados (dlt state)

**Files:**
- Modify: `src/contratos_publicos_ingest/sources.py`
- Test: `tests/test_sources.py` (extend the file created in Task 3)

**Interfaces:**
- Consumes: `Periodo` dataclass (`ano: int`, `mes: int | None`) already defined in `sources.py`.
- Produces: `sources._es_periodo_abierto(periodo: Periodo, hoy: date) -> bool`, `sources._periodos_pendientes(periodos: list[Periodo], watermark: tuple[int, int] | None, hoy: date) -> list[Periodo]`.

- [ ] **Step 1: Write the failing tests**

At the top of `tests/test_sources.py`, add `from datetime import date` and extend the
existing `from contratos_publicos_ingest.sources import _descargar_zip` line so it reads:

```python
from contratos_publicos_ingest.sources import (
    Periodo,
    _descargar_zip,
    _es_periodo_abierto,
    _periodos_pendientes,
)
```

Then append these test functions at the end of the file:

```python
def test_periodo_anual_abierto_solo_en_el_ano_actual():
    hoy = date(2026, 8, 18)

    assert _es_periodo_abierto(Periodo(ano=2026, mes=None), hoy) is True
    assert _es_periodo_abierto(Periodo(ano=2025, mes=None), hoy) is False


def test_periodo_mensual_abierto_solo_en_mes_actual():
    hoy = date(2026, 8, 18)

    assert _es_periodo_abierto(Periodo(ano=2026, mes=8), hoy) is True
    assert _es_periodo_abierto(Periodo(ano=2026, mes=7), hoy) is False
    assert _es_periodo_abierto(Periodo(ano=2025, mes=8), hoy) is False


def test_periodos_pendientes_sin_watermark_devuelve_todos():
    hoy = date(2026, 8, 18)
    periodos = [Periodo(ano=2024, mes=None), Periodo(ano=2025, mes=1)]

    assert _periodos_pendientes(periodos, None, hoy) == periodos


def test_periodos_pendientes_salta_cerrados_hasta_watermark():
    hoy = date(2026, 8, 18)
    periodos = [
        Periodo(ano=2025, mes=1),
        Periodo(ano=2025, mes=2),
        Periodo(ano=2026, mes=8),  # abierto: nunca se salta
    ]
    watermark = (2025, 1)

    pendientes = _periodos_pendientes(periodos, watermark, hoy)

    assert pendientes == [Periodo(ano=2025, mes=2), Periodo(ano=2026, mes=8)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_sources.py -v`
Expected: FAIL — `_es_periodo_abierto` and `_periodos_pendientes` don't exist yet (`ImportError`).

- [ ] **Step 3: Add the watermark logic and wire it into the resource in `src/contratos_publicos_ingest/sources.py`**

Add these two functions right after `periodos_en_rango`:

```python
def _es_periodo_abierto(periodo: Periodo, hoy: date) -> bool:
    """Un periodo está abierto si es el año o mes en curso: aún puede recibir altas."""
    if periodo.ano != hoy.year:
        return False
    return periodo.mes is None or periodo.mes == hoy.month


def _periodos_pendientes(
    periodos: list[Periodo], watermark: tuple[int, int] | None, hoy: date
) -> list[Periodo]:
    """Filtra los periodos cerrados ya cubiertos por el watermark.

    El watermark se compara como tupla (ano, mes o 0), no como periodo_str: comparar
    strings de distinta longitud entre periodos anuales ("2024") y mensuales ("202501")
    no es un orden robusto.
    """
    if watermark is None:
        return periodos
    return [
        periodo
        for periodo in periodos
        if _es_periodo_abierto(periodo, hoy) or (periodo.ano, periodo.mes or 0) > watermark
    ]
```

Replace the `licitaciones_nacional` resource body:

```python
@dlt.resource(name="licitaciones", write_disposition="merge", primary_key="id")
def licitaciones_nacional(
    ano_inicio: int = FIRST_YEAR, ano_fin: int | None = None
) -> Iterator[Licitacion]:
    """Licitaciones de PLACSP (sindicacion_643), excluyendo contratos menores.

    Cada ZIP se descarga en memoria, se parsea y se descarta: no se persiste nada en
    disco. El `write_disposition="merge"` sobre `id` deduplica automáticamente, así que
    re-ejecutar el pipeline sobre el mismo rango de años es seguro (aunque vuelve a
    descargar y reprocesar todo, ya que no hay caché).
    """
    ano_fin = ano_fin or date.today().year
    session = _get_session()

    for periodo in periodos_en_rango(ano_inicio, ano_fin):
        data = _descargar_zip(session, periodo.url)
        if data is None:
            continue
        yield from _entries_from_zip_bytes(data)
        time.sleep(0.3)
```

with:

```python
@dlt.resource(name="licitaciones", write_disposition="merge", primary_key="id")
def licitaciones_nacional(
    ano_inicio: int = FIRST_YEAR, ano_fin: int | None = None
) -> Iterator[Licitacion]:
    """Licitaciones de PLACSP (sindicacion_643), excluyendo contratos menores.

    Cada ZIP se descarga en memoria, se parsea y se descarta: no se persiste nada en
    disco. El `write_disposition="merge"` sobre `id` deduplica automáticamente en el
    destino. Además, un watermark en el state de dlt evita redescargar periodos cerrados
    ya cargados con éxito en una ejecución anterior; el periodo abierto (año/mes en
    curso) siempre se reprocesa.
    """
    ano_fin = ano_fin or date.today().year
    hoy = date.today()
    session = _get_session()

    state = dlt.current.resource_state()
    watermark_lista = state.get("ultimo_periodo_cerrado")
    watermark = tuple(watermark_lista) if watermark_lista is not None else None

    periodos = _periodos_pendientes(periodos_en_rango(ano_inicio, ano_fin), watermark, hoy)

    for periodo in periodos:
        data = _descargar_zip(session, periodo.url)
        if data is None:
            continue
        yield from _entries_from_zip_bytes(data)

        if not _es_periodo_abierto(periodo, hoy):
            clave = (periodo.ano, periodo.mes or 0)
            if watermark is None or clave > watermark:
                watermark = clave
                state["ultimo_periodo_cerrado"] = list(watermark)

        time.sleep(0.3)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_sources.py -v`
Expected: PASS (7 tests total in the file)

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest -v`
Expected: PASS (all tests across `tests/test_parsing.py`, `tests/test_pipeline.py`, `tests/test_sources.py`)

- [ ] **Step 6: Update the README "Cómo funciona" section**

In `README.md`, in the `## Cómo funciona` section, replace the bullet:

```markdown
- La carga usa `write_disposition="merge"` con `id` como clave primaria, así que
  re-ejecutar el pipeline sobre el mismo rango de años es seguro y no genera duplicados
  (aunque sí vuelve a descargar y reprocesar todo, al no haber caché en disco).
```

with:

```markdown
- La carga usa `write_disposition="merge"` con `id` como clave primaria, así que
  re-ejecutar el pipeline sobre el mismo rango de años es seguro y no genera duplicados.
  Además, un watermark guardado en el state de dlt evita redescargar periodos cerrados
  ya cargados con éxito: solo se reprocesan los periodos nuevos y el periodo abierto
  (año o mes en curso).
```

- [ ] **Step 7: Commit**

```bash
git add src/contratos_publicos_ingest/sources.py tests/test_sources.py README.md
git commit -m "Añade watermark en el state de dlt para saltar periodos ya cargados"
```
