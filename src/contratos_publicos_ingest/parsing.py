"""Parsing de las entradas ATOM/CODICE de licitaciones a diccionarios planos."""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from typing import Any, Iterator

from .settings import ESTADOS, NS, PROCEDIMIENTOS, TIPOS_CONTRATO


def _safe_text(element: ET.Element | None, xpath: str) -> str | None:
    if element is None:
        return None
    found = element.find(xpath, NS)
    if found is not None and found.text:
        return found.text.strip()
    return None


def _safe_attr(element: ET.Element | None, xpath: str, attr: str) -> str | None:
    if element is None:
        return None
    found = element.find(xpath, NS)
    if found is not None:
        return found.get(attr)
    return None


def _safe_float(text: str | None) -> float | None:
    if text is None:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


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

        expediente = _safe_text(status, "cbc:ContractFolderID")
        estado_code = _safe_text(status, "cbc-place-ext:ContractFolderStatusCode")

        located_party = status.find("cac-place-ext:LocatedContractingParty", NS)
        party = located_party.find("cac:Party", NS) if located_party is not None else None

        nombre_organo = _safe_text(party, "cac:PartyName/cbc:Name")
        ciudad_organo = _safe_text(party, "cac:PostalAddress/cbc:CityName")

        nif_organo = None
        dir3_organo = None
        id_plataforma = None
        if party is not None:
            for pid in party.findall("cac:PartyIdentification", NS):
                id_elem = pid.find("cbc:ID", NS)
                if id_elem is not None and id_elem.text:
                    scheme = id_elem.get("schemeName", "")
                    if scheme == "NIF":
                        nif_organo = id_elem.text.strip()
                    elif scheme == "DIR3":
                        dir3_organo = id_elem.text.strip()
                    elif scheme == "ID_PLATAFORMA":
                        id_plataforma = id_elem.text.strip()

        parent_names = []
        parent = (
            located_party.find("cac-place-ext:ParentLocatedParty", NS)
            if located_party is not None
            else None
        )
        while parent is not None:
            pname = _safe_text(parent, "cac:PartyName/cbc:Name")
            if pname:
                parent_names.append(pname)
            parent = parent.find("cac-place-ext:ParentLocatedParty", NS)
        dependencia = " > ".join(reversed(parent_names)) if parent_names else None

        project = status.find("cac:ProcurementProject", NS)
        objeto = _safe_text(project, "cbc:Name")
        tipo_code = _safe_text(project, "cbc:TypeCode")
        subtipo_code = _safe_text(project, "cbc:SubTypeCode")

        budget = project.find("cac:BudgetAmount", NS) if project is not None else None
        valor_estimado_contrato = _safe_float(
            _safe_text(budget, "cbc:EstimatedOverallContractAmount")
        )
        importe_con_iva = _safe_float(_safe_text(budget, "cbc:TotalAmount"))
        importe_sin_iva = _safe_float(_safe_text(budget, "cbc:TaxExclusiveAmount"))

        cpvs = []
        if project is not None:
            for cpv_elem in project.findall(
                ".//cac:RequiredCommodityClassification/cbc:ItemClassificationCode", NS
            ):
                if cpv_elem.text:
                    cpvs.append(cpv_elem.text.strip())
        cpv_principal = cpvs[0] if cpvs else None
        cpvs_todos = ";".join(cpvs) if cpvs else None

        ubicacion = _safe_text(project, ".//cac:RealizedLocation/cbc:CountrySubentity")
        nuts = _safe_text(project, ".//cac:RealizedLocation/cbc:CountrySubentityCode")

        duracion = _safe_text(project, ".//cac:PlannedPeriod/cbc:DurationMeasure")
        duracion_unidad = _safe_attr(
            project, ".//cac:PlannedPeriod/cbc:DurationMeasure", "unitCode"
        )

        process = status.find("cac:TenderingProcess", NS)
        procedimiento_code = _safe_text(process, "cbc:ProcedureCode")
        urgencia = _safe_text(process, "cbc:UrgencyCode")

        fecha_limite = _safe_text(
            process, ".//cac:TenderSubmissionDeadlinePeriod/cbc:EndDate"
        )
        hora_limite = _safe_text(
            process, ".//cac:TenderSubmissionDeadlinePeriod/cbc:EndTime"
        )

        terms = status.find("cac:TenderingTerms", NS)
        financiacion_ue = _safe_text(terms, "cbc:FundingProgramCode")

        result = status.find("cac:TenderResult", NS)
        adjudicatario = None
        nif_adjudicatario = None
        importe_adjudicacion = None
        importe_adj_con_iva = None
        fecha_adjudicacion = None
        num_ofertas = None
        es_pyme = None

        if result is not None:
            adjudicatario = _safe_text(result, ".//cac:WinningParty/cac:PartyName/cbc:Name")

            winner_id = result.find(".//cac:WinningParty/cac:PartyIdentification/cbc:ID", NS)
            if winner_id is not None and winner_id.text:
                nif_adjudicatario = winner_id.text.strip()

            importe_adjudicacion = _safe_float(
                _safe_text(
                    result,
                    ".//cac:AwardedTenderedProject/cac:LegalMonetaryTotal/cbc:TaxExclusiveAmount",
                )
            )
            importe_adj_con_iva = _safe_float(
                _safe_text(
                    result,
                    ".//cac:AwardedTenderedProject/cac:LegalMonetaryTotal/cbc:PayableAmount",
                )
            )

            fecha_adjudicacion = _safe_text(result, "cbc:AwardDate")

            val = _safe_text(result, "cbc:ReceivedTenderQuantity")
            if val is not None:
                try:
                    num_ofertas = int(val)
                except ValueError:
                    num_ofertas = None

            pyme = _safe_text(result, "cbc:SMEAwardedIndicator")
            es_pyme = pyme == "true" if pyme else None

        fecha_updated = _safe_text(entry, "atom:updated")
        valid_notice = status.find("cac-place-ext:ValidNoticeInfo", NS)
        fecha_publicacion = _safe_text(
            valid_notice,
            ".//cac-place-ext:AdditionalPublicationDocumentReference/cbc:IssueDate",
        )

        return {
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
    except Exception:
        return None


def iter_entries_from_atom_bytes(data: bytes) -> Iterator[dict[str, Any]]:
    """Itera las licitaciones contenidas en el XML .atom (en memoria, sin tocar disco)."""
    try:
        for _, elem in ET.iterparse(io.BytesIO(data), events=("end",)):
            if elem.tag == "{http://www.w3.org/2005/Atom}entry":
                lic = parse_entry(elem)
                if lic:
                    yield lic
                elem.clear()
    except ET.ParseError:
        root = ET.fromstring(data)
        for entry in root.findall("atom:entry", NS):
            lic = parse_entry(entry)
            if lic:
                yield lic
