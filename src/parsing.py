import tempfile
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from pathlib import Path

from pydantic import BaseModel, Field

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "cbc": "urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:dgpe:names:draft:codice:schema:xsd:CommonAggregateComponents-2",
    "cac-place-ext": "urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2",
    "cbc-place-ext": "urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonBasicComponents-2",
}

# Official code lists, from OpenPLACSP's bundled genericode files
# (ContractCode-2.08.gc, SyndicationTenderingProcessCode-2.07.gc, SyndicationContractFolderStatusCode-2.04.gc)
CONTRACT_TYPES = {
    "1": "Suministros",
    "2": "Servicios",
    "3": "Obras",
    "21": "Gestión de Servicios Públicos",
    "22": "Concesión de Servicios",
    "31": "Concesión de Obras Públicas",
    "32": "Concesión de Obras",
    "40": "Colaboración entre el sector público y sector privado",
    "7": "Administrativo especial",
    "8": "Privado",
    "50": "Patrimonial",
}

PROCEDURE_TYPES = {
    "1": "Abierto",
    "2": "Restringido",
    "3": "Negociado sin publicidad",
    "4": "Negociado con publicidad",
    "5": "Diálogo competitivo",
    "6": "Contrato menor",
    "7": "Derivado de acuerdo marco",
    "8": "Concurso de proyectos",
    "9": "Abierto simplificado",
    "10": "Asociación para la innovación",
    "11": "Derivado de asociación para la innovación",
    "12": "Basado en un sistema dinámico de adquisición",
    "13": "Licitación con negociación",
    "100": "Normas internas",
    "999": "Otros",
}

STATUS_CODES = {
    "PRE": "Anuncio Previo",
    "PUB": "En plazo",
    "EV": "Pendiente de adjudicación",
    "ADJ": "Adjudicada",
    "RES": "Resuelta",
    "ANUL": "Anulada",
}

# TenderResultCode-2.09.gc
RESULT_CODES = {
    "1": "Adjudicado Provisionalmente",
    "2": "Adjudicado Definitivamente",
    "3": "Desierto",
    "4": "Desistimiento",
    "5": "Renuncia",
    "6": "Desierto Provisionalmente",
    "7": "Desierto Definitivamente",
    "8": "Adjudicado",
    "9": "Formalizado",
    "10": "Licitador mejor valorado",
    "11": "Encargo Formalizado",
}


class Notice(BaseModel):
    tipo_code: str | None = None
    fecha: str | None = None


class Document(BaseModel):
    tipo: str
    nombre: str | None = None
    url: str | None = None


class QualificationCriterion(BaseModel):
    tipo: str
    descripcion: str | None = None


class AwardingCriterion(BaseModel):
    tipo_code: str | None = None
    descripcion: str | None = None
    peso: float | None = None


class TenderRecord(BaseModel):
    id: str
    url: str | None = None
    fecha_updated: str | None = None
    expediente: str | None = None
    estado_code: str | None = None
    estado: str | None = None
    organo_nombre: str | None = None
    organo_nif: str | None = None
    organo_dir3: str | None = None
    id_plataforma: str | None = None
    organo_ciudad: str | None = None
    organo_tipo_code: str | None = None
    organo_actividad_code: str | None = None
    organo_telefono: str | None = None
    organo_email: str | None = None
    organo_direccion: str | None = None
    organo_cp: str | None = None
    dependencia: str | None = None
    objeto: str | None = None
    tipo_contrato_code: str | None = None
    tipo_contrato: str | None = None
    subtipo_code: str | None = None
    contrato_mixto: bool | None = None
    procedimiento_code: str | None = None
    procedimiento: str | None = None
    importe_estimado: float | None = None
    importe_sin_iva: float | None = None
    importe_con_iva: float | None = None
    cpv_principal: str | None = None
    cpvs: str | None = None
    ubicacion: str | None = None
    nuts: str | None = None
    duracion: str | None = None
    duracion_unidad: str | None = None
    urgencia: str | None = None
    fecha_limite: str | None = None
    hora_limite: str | None = None
    sobre_umbral: bool | None = None
    subasta_electronica: bool | None = None
    financiacion_ue: str | None = None
    resultado_code: str | None = None
    resultado: str | None = None
    fecha_adjudicacion: str | None = None
    num_ofertas: int | None = None
    num_ofertas_pyme: int | None = None
    es_pyme: bool | None = None
    adjudicatario: str | None = None
    nif_adjudicatario: str | None = None
    ciudad_adjudicatario: str | None = None
    importe_adjudicacion_sin_iva: float | None = None
    importe_adjudicacion_con_iva: float | None = None
    contrato_id: str | None = None
    contrato_fecha: str | None = None
    avisos: list[Notice] = Field(default_factory=list)
    documentos: list[Document] = Field(default_factory=list)
    criterios_solvencia: list[QualificationCriterion] = Field(default_factory=list)
    criterios_adjudicacion: list[AwardingCriterion] = Field(default_factory=list)


def _text(element: ET.Element | None, xpath: str) -> str | None:
    if element is None:
        return None
    found = element.find(xpath, NS)
    if found is not None and found.text:
        return found.text.strip()
    return None


def _attr(element: ET.Element | None, xpath: str, attr: str) -> str | None:
    if element is None:
        return None
    found = element.find(xpath, NS)
    return found.get(attr) if found is not None else None


def _document_refs(elements: list[ET.Element], tipo: str) -> list[Document]:
    return [
        Document(
            tipo=tipo,
            nombre=_text(ref, "cbc:ID"),
            url=_text(ref, "cac:Attachment/cac:ExternalReference/cbc:URI"),
        )
        for ref in elements
    ]


def parse_entry(entry: ET.Element) -> TenderRecord:
    status = entry.find("cac-place-ext:ContractFolderStatus", NS)
    located_party = status.find("cac-place-ext:LocatedContractingParty", NS)
    party = located_party.find("cac:Party", NS) if located_party is not None else None
    project = status.find("cac:ProcurementProject", NS)

    organo_nif = organo_dir3 = id_plataforma = None
    if party is not None:
        for party_id in party.findall("cac:PartyIdentification/cbc:ID", NS):
            scheme = party_id.get("schemeName")
            if scheme == "NIF":
                organo_nif = party_id.text.strip() if party_id.text else None
            elif scheme == "DIR3":
                organo_dir3 = party_id.text.strip() if party_id.text else None
            elif scheme == "ID_PLATAFORMA":
                id_plataforma = party_id.text.strip() if party_id.text else None

    parent_names = []
    parent = located_party.find("cac-place-ext:ParentLocatedParty", NS) if located_party is not None else None
    while parent is not None:
        name = _text(parent, "cac:PartyName/cbc:Name")
        if name:
            parent_names.append(name)
        parent = parent.find("cac-place-ext:ParentLocatedParty", NS)
    dependencia = " > ".join(reversed(parent_names)) if parent_names else None

    importe_estimado_text = _text(project, "cac:BudgetAmount/cbc:EstimatedOverallContractAmount")
    importe_sin_iva_text = _text(project, "cac:BudgetAmount/cbc:TaxExclusiveAmount")
    importe_con_iva_text = _text(project, "cac:BudgetAmount/cbc:TotalAmount")
    tipo_contrato_code = _text(project, "cbc:TypeCode")
    subtipo_code = _text(project, "cbc:SubTypeCode")
    contrato_mixto_text = _text(project, "cbc:MixContractIndicator")
    process = status.find("cac:TenderingProcess", NS)
    procedimiento_code = _text(process, "cbc:ProcedureCode")
    sobre_umbral_text = _text(process, "cbc:OverThresholdIndicator")
    subasta_electronica_text = _text(process, "cac:AuctionTerms/cbc:AuctionConstraintIndicator")
    estado_code = _text(status, "cbc-place-ext:ContractFolderStatusCode")

    cpvs = []
    if project is not None:
        for cpv in project.findall("cac:RequiredCommodityClassification/cbc:ItemClassificationCode", NS):
            if cpv.text:
                cpvs.append(cpv.text.strip())

    terms = status.find("cac:TenderingTerms", NS)

    result = status.find("cac:TenderResult", NS)
    resultado_code = _text(result, "cbc:ResultCode")
    num_ofertas_text = _text(result, "cbc:ReceivedTenderQuantity")
    num_ofertas_pyme_text = _text(result, "cbc:SMEsReceivedTenderQuantity")
    es_pyme_text = _text(result, "cbc:SMEAwardedIndicator")
    importe_adj_sin_iva_text = _text(result, "cac:AwardedTenderedProject/cac:LegalMonetaryTotal/cbc:TaxExclusiveAmount")
    importe_adj_con_iva_text = _text(result, "cac:AwardedTenderedProject/cac:LegalMonetaryTotal/cbc:PayableAmount")

    avisos = [
        Notice(
            tipo_code=_text(notice, "cbc-place-ext:NoticeTypeCode"),
            fecha=_text(notice, ".//cac-place-ext:AdditionalPublicationDocumentReference/cbc:IssueDate"),
        )
        for notice in status.findall("cac-place-ext:ValidNoticeInfo", NS)
    ]

    documentos = (
        _document_refs(status.findall("cac:LegalDocumentReference", NS), "legal")
        + _document_refs(status.findall("cac:TechnicalDocumentReference", NS), "technical")
        + _document_refs(status.findall("cac:AdditionalDocumentReference", NS), "additional")
        + _document_refs(
            status.findall("cac-place-ext:GeneralDocument/cac-place-ext:GeneralDocumentDocumentReference", NS),
            "general",
        )
    )

    qualification = terms.find("cac:TendererQualificationRequest", NS) if terms is not None else None
    criterios_solvencia = []
    if qualification is not None:
        for tag, tipo in [
            ("cac:TechnicalEvaluationCriteria", "tecnica"),
            ("cac:FinancialEvaluationCriteria", "financiera"),
            ("cac:SpecificTendererRequirement", "especifica"),
        ]:
            for criterion in qualification.findall(tag, NS):
                criterios_solvencia.append(
                    QualificationCriterion(tipo=tipo, descripcion=_text(criterion, "cbc:Description"))
                )

    awarding = terms.find("cac:AwardingTerms", NS) if terms is not None else None
    criterios_adjudicacion = []
    if awarding is not None:
        for criterion in awarding.findall("cac:AwardingCriteria", NS):
            peso_text = _text(criterion, "cbc:WeightNumeric")
            criterios_adjudicacion.append(
                AwardingCriterion(
                    tipo_code=_text(criterion, "cbc:AwardingCriteriaTypeCode"),
                    descripcion=_text(criterion, "cbc:Description"),
                    peso=float(peso_text) if peso_text else None,
                )
            )

    return TenderRecord(
        id=_text(entry, "atom:id"),
        url=_attr(entry, "atom:link", "href"),
        fecha_updated=_text(entry, "atom:updated"),
        expediente=_text(status, "cbc:ContractFolderID"),
        estado_code=estado_code,
        estado=STATUS_CODES.get(estado_code, estado_code),
        organo_nombre=_text(party, "cac:PartyName/cbc:Name"),
        organo_nif=organo_nif,
        organo_dir3=organo_dir3,
        id_plataforma=id_plataforma,
        organo_ciudad=_text(party, "cac:PostalAddress/cbc:CityName"),
        organo_tipo_code=_text(located_party, "cbc:ContractingPartyTypeCode"),
        organo_actividad_code=_text(located_party, "cbc:ActivityCode"),
        organo_telefono=_text(party, "cac:Contact/cbc:Telephone"),
        organo_email=_text(party, "cac:Contact/cbc:ElectronicMail"),
        organo_direccion=_text(party, "cac:PostalAddress/cac:AddressLine/cbc:Line"),
        organo_cp=_text(party, "cac:PostalAddress/cbc:PostalZone"),
        dependencia=dependencia,
        objeto=_text(project, "cbc:Name"),
        tipo_contrato_code=tipo_contrato_code,
        tipo_contrato=CONTRACT_TYPES.get(tipo_contrato_code, tipo_contrato_code),
        subtipo_code=subtipo_code,
        contrato_mixto=contrato_mixto_text == "true" if contrato_mixto_text else None,
        procedimiento_code=procedimiento_code,
        procedimiento=PROCEDURE_TYPES.get(procedimiento_code, procedimiento_code),
        importe_estimado=float(importe_estimado_text) if importe_estimado_text else None,
        importe_sin_iva=float(importe_sin_iva_text) if importe_sin_iva_text else None,
        importe_con_iva=float(importe_con_iva_text) if importe_con_iva_text else None,
        cpv_principal=cpvs[0] if cpvs else None,
        cpvs=";".join(cpvs) if cpvs else None,
        ubicacion=_text(project, "cac:RealizedLocation/cbc:CountrySubentity"),
        nuts=_text(project, "cac:RealizedLocation/cbc:CountrySubentityCode"),
        duracion=_text(project, "cac:PlannedPeriod/cbc:DurationMeasure"),
        duracion_unidad=_attr(project, "cac:PlannedPeriod/cbc:DurationMeasure", "unitCode"),
        urgencia=_text(process, "cbc:UrgencyCode"),
        fecha_limite=_text(process, "cac:TenderSubmissionDeadlinePeriod/cbc:EndDate"),
        hora_limite=_text(process, "cac:TenderSubmissionDeadlinePeriod/cbc:EndTime"),
        sobre_umbral=sobre_umbral_text == "true" if sobre_umbral_text else None,
        subasta_electronica=subasta_electronica_text == "true" if subasta_electronica_text else None,
        financiacion_ue=_text(terms, "cbc:FundingProgramCode"),
        resultado_code=resultado_code,
        resultado=RESULT_CODES.get(resultado_code, resultado_code),
        fecha_adjudicacion=_text(result, "cbc:AwardDate"),
        num_ofertas=int(num_ofertas_text) if num_ofertas_text else None,
        num_ofertas_pyme=int(num_ofertas_pyme_text) if num_ofertas_pyme_text else None,
        es_pyme=es_pyme_text == "true" if es_pyme_text else None,
        adjudicatario=_text(result, "cac:WinningParty/cac:PartyName/cbc:Name"),
        nif_adjudicatario=_text(result, "cac:WinningParty/cac:PartyIdentification/cbc:ID"),
        ciudad_adjudicatario=_text(result, "cac:WinningParty/cac:PhysicalLocation/cac:Address/cbc:CityName"),
        importe_adjudicacion_sin_iva=float(importe_adj_sin_iva_text) if importe_adj_sin_iva_text else None,
        importe_adjudicacion_con_iva=float(importe_adj_con_iva_text) if importe_adj_con_iva_text else None,
        contrato_id=_text(result, "cac:Contract/cbc:ID"),
        contrato_fecha=_text(result, "cac:Contract/cbc:IssueDate"),
        avisos=avisos,
        documentos=documentos,
        criterios_solvencia=criterios_solvencia,
        criterios_adjudicacion=criterios_adjudicacion,
    )


def parse_atom_file(path: Path) -> Iterator[TenderRecord]:
    for _, elem in ET.iterparse(str(path), events=("end",)):
        if elem.tag == "{http://www.w3.org/2005/Atom}entry":
            yield parse_entry(elem)
            elem.clear()


def parse_zip(path: Path) -> Iterator[TenderRecord]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        with zipfile.ZipFile(path) as zf:
            zf.extractall(tmp_path)
        for atom_file in tmp_path.rglob("*.atom"):
            yield from parse_atom_file(atom_file)
