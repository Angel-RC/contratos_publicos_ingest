"""Configuración estática del scraper de licitaciones nacionales (PLACSP)."""

from __future__ import annotations

BASE_URL = "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/"
FILE_PATTERN = "licitacionesPerfilesContratanteCompleto3_{periodo}.zip"

# Primer año con datos disponibles para este conjunto.
FIRST_YEAR = 2012

# A partir de este año, la plataforma publica un ZIP por mes en vez de uno por año.
MONTHLY_SINCE_YEAR = 2025

# Namespaces del XML CODICE/ATOM que usa la Plataforma de Contratación del Sector Público.
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "cbc": "urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:dgpe:names:draft:codice:schema:xsd:CommonAggregateComponents-2",
    "cbc-place-ext": "urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonBasicComponents-2",
    "cac-place-ext": "urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2",
}

TIPOS_CONTRATO = {
    "1": "Suministros",
    "2": "Servicios",
    "3": "Obras",
    "21": "Gestión Servicios Públicos",
    "31": "Concesión Obras",
    "40": "Concesión Servicios",
    "7": "Administrativo Especial",
    "8": "Privado",
    "50": "Patrimonial",
    "22": "22",
}

ESTADOS = {
    "PUB": "Publicada",
    "EV": "En evaluación",
    "ADJ": "Adjudicada",
    "RES": "Resuelta",
    "ANUL": "Anulada",
    "DES": "Desierta",
}

PROCEDIMIENTOS = {
    "1": "Abierto",
    "2": "Restringido",
    "3": "Negociado con publicidad",
    "4": "Negociado sin publicidad",
    "5": "Diálogo competitivo",
    "6": "Asociación innovación",
    "100": "Basado en acuerdo marco",
    "999": "Otros",
}

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
