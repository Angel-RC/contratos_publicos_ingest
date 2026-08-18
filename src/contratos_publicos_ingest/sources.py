"""Fuente dlt: descarga en memoria y parsea los ZIP de licitaciones nacionales (PLACSP)."""

from __future__ import annotations

import io
import time
import zipfile
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterator

import dlt
import requests

from .parsing import iter_entries_from_atom_bytes
from .settings import BASE_URL, FILE_PATTERN, FIRST_YEAR, MONTHLY_SINCE_YEAR, USER_AGENT


@dataclass(frozen=True)
class Periodo:
    ano: int
    mes: int | None  # None => archivo anual

    @property
    def periodo_str(self) -> str:
        return f"{self.ano}{self.mes:02d}" if self.mes is not None else str(self.ano)

    @property
    def nombre_archivo(self) -> str:
        return FILE_PATTERN.format(periodo=self.periodo_str)

    @property
    def url(self) -> str:
        return BASE_URL + self.nombre_archivo


def periodos_en_rango(ano_inicio: int, ano_fin: int) -> list[Periodo]:
    """Genera los periodos (anuales o mensuales, según corresponda) entre dos años."""
    hoy = date.today()
    ano_inicio = max(ano_inicio, FIRST_YEAR)

    periodos: list[Periodo] = []
    for ano in range(ano_inicio, ano_fin + 1):
        usar_mensual = ano >= MONTHLY_SINCE_YEAR
        if usar_mensual:
            max_mes = hoy.month if ano == hoy.year else 12
            for mes in range(1, max_mes + 1):
                periodos.append(Periodo(ano=ano, mes=mes))
        else:
            periodos.append(Periodo(ano=ano, mes=None))
    return periodos


def _get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        }
    )
    return session


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


def _entries_from_zip_bytes(data: bytes) -> Iterator[dict[str, Any]]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            if name.endswith(".atom"):
                yield from iter_entries_from_atom_bytes(zf.read(name))


@dlt.resource(name="licitaciones", write_disposition="merge", primary_key="id")
def licitaciones_nacional(
    ano_inicio: int = FIRST_YEAR, ano_fin: int | None = None
) -> Iterator[dict[str, Any]]:
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


@dlt.source(name="placsp")
def placsp_source(ano_inicio: int = FIRST_YEAR, ano_fin: int | None = None):
    return licitaciones_nacional(ano_inicio=ano_inicio, ano_fin=ano_fin)
