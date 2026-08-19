import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from parsing import parse_atom_file, parse_entry, parse_zip

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_atom_file_parses_every_entry():
    records = parse_atom_file(FIXTURES / "sample_feed.atom")

    assert [r.expediente for r in records] == ["2026/ETSAE0226/00004805E", "TSA0082946"]


def test_parse_zip_parses_atom_files_inside(tmp_path):
    zip_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(FIXTURES / "sample_feed.atom", arcname="sample_feed.atom")

    records = parse_zip(zip_path)

    assert [r.expediente for r in records] == ["2026/ETSAE0226/00004805E", "TSA0082946"]


def test_parse_entry_extracts_core_fields():
    entry = ET.parse(FIXTURES / "entry_no_result.xml").getroot()

    record = parse_entry(entry)

    assert record.id == "https://contrataciondelestado.es/sindicacion/licitacionesPerfilContratante/20050375"
    assert record.url == "https://contrataciondelestado.es/wps/poc?uri=deeplink:detalle_licitacion&idEvl=%2BoE6xidT15qExvMJXBMHHQ%3D%3D"
    assert record.expediente == "2026/ETSAE0226/00004805E"
    assert record.estado_code == "EV"
    assert record.estado == "Pendiente de adjudicación"
    assert record.organo_nombre == "Jefatura de Intendencia de Asuntos Económicos Sur"
    assert record.organo_nif == "S4130025B"
    assert record.organo_dir3 == "EA0003104"
    assert record.organo_ciudad == "Sevilla"
    assert record.objeto == "Contrato servicio peluquería y tratamiento de belleza en el CDM HISPALIS (Sevilla)."
    assert record.tipo_contrato_code == "22"
    assert record.tipo_contrato == "Concesión de Servicios"
    assert record.procedimiento_code == "9"
    assert record.procedimiento == "Abierto simplificado"
    assert record.importe_estimado == 139490.92
    assert record.importe_sin_iva == 0
    assert record.importe_con_iva == 0
    assert record.cpv_principal == "98320000"
    assert record.cpvs == "98320000"
    assert record.ubicacion == "Sevilla"
    assert record.nuts == "ES618"
    assert record.duracion == "2"
    assert record.duracion_unidad == "ANN"
    assert record.fecha_updated == "2026-07-31T09:09:35.658+02:00"
    assert record.subtipo_code is None
    assert record.contrato_mixto is False
    assert record.sobre_umbral is False
    assert record.subasta_electronica is False
    assert record.urgencia == "1"
    assert record.fecha_limite == "2026-07-30"
    assert record.hora_limite == "09:00:00"
    assert record.financiacion_ue == "NO-EU"
    assert record.resultado_code is None
    assert record.adjudicatario is None
    assert [(a.tipo_code, a.fecha) for a in record.avisos] == [
        ("DOC_CD", "2026-07-14"),
        ("DOC_CN", "2026-07-14"),
    ]
    assert len(record.documentos) == 1 + 1 + 5 + 7
    legal_docs = [d for d in record.documentos if d.tipo == "legal"]
    assert legal_docs[0].nombre == "04 PCAP 4805.pdf"
    assert legal_docs[0].url.startswith("https://contrataciondelestado.es/FileSystem")
    assert len(record.criterios_solvencia) == 1 + 1 + 5
    assert {c.tipo for c in record.criterios_solvencia} == {"tecnica", "financiera", "especifica"}
    tecnica = next(c for c in record.criterios_solvencia if c.tipo == "tecnica")
    assert tecnica.descripcion.startswith("Según lo establecido en el PCAP")
    assert [(c.descripcion, c.peso) for c in record.criterios_adjudicacion] == [
        ("MEJOR RELACIÓN CALIDAD-PRECIO", 70),
        ("MAYOR RELACIÓN DE MEJORAS", 30),
    ]
    assert record.id_plataforma == "10000140000442"
    assert record.organo_tipo_code == "1"
    assert record.organo_actividad_code == "2"
    assert record.organo_telefono == "954248459"
    assert record.organo_email == "jiaesur_contratacion@mde.es"
    assert record.organo_direccion == "Avda. de la Borbolla 27"
    assert record.organo_cp == "41013"
    assert record.dependencia == (
        "Sector Público > ADMINISTRACIÓN GENERAL DEL ESTADO > Ministerio de Defensa"
        " > Ejército de Tierra > SAECO de la Jefatura de Intendencia de Asuntos Económicos del Sur"
    )


def test_parse_entry_without_dir3_leaves_it_as_none():
    entry = ET.parse(FIXTURES / "entry_with_result.xml").getroot()

    record = parse_entry(entry)

    assert record.url == "https://contrataciondelestado.es/wps/poc?uri=deeplink:detalle_licitacion&idEvl=0hedDuB2M%2Fr9pbnDwlaUlg%3D%3D"
    assert record.expediente == "TSA0082946"
    assert record.estado_code == "RES"
    assert record.estado == "Resuelta"
    assert record.organo_nombre == "Empresa de Transformación Agraria S.A.,S.M.E., M.P., (TRAGSA)"
    assert record.organo_nif == "A28476208"
    assert record.organo_dir3 is None
    assert record.organo_ciudad == "Madrid"
    assert record.tipo_contrato_code == "1"
    assert record.tipo_contrato == "Suministros"
    assert record.importe_estimado == 25806.11
    assert record.importe_sin_iva == 25806.11
    assert record.importe_con_iva == 31225.39
    assert record.cpv_principal == "34928471"
    assert record.ubicacion == "Huesca"
    assert record.nuts == "ES241"
    assert record.duracion == "4"
    assert record.duracion_unidad == "MON"
    assert record.fecha_updated == "2026-07-31T09:09:07.733+02:00"
    assert record.subtipo_code == "2"
    assert record.contrato_mixto is False
    assert record.sobre_umbral is False
    assert record.subasta_electronica is False
    assert record.financiacion_ue == "NO-EU"
    assert record.resultado_code == "9"
    assert record.resultado == "Formalizado"
    assert record.fecha_adjudicacion == "2026-04-22"
    assert record.num_ofertas == 5
    assert record.num_ofertas_pyme == 5
    assert record.es_pyme is True
    assert record.adjudicatario == "Estampaciones casado SL"
    assert record.nif_adjudicatario == "B14053854"
    assert record.ciudad_adjudicatario == "Córdoba"
    assert record.importe_adjudicacion_sin_iva == 17401.44
    assert record.importe_adjudicacion_con_iva == 21055.74
    assert record.contrato_id == "860002"
    assert record.contrato_fecha == "2026-04-27"
    assert [(a.tipo_code, a.fecha) for a in record.avisos] == [
        ("DOC_CAN_ADJ", "2026-04-27"),
        ("DOC_CD", "2026-03-12"),
        ("DOC_CN", "2026-03-12"),
        ("DOC_FORM", "2026-04-28"),
    ]
    assert len(record.documentos) == 1 + 1 + 1 + 5
    assert {d.tipo for d in record.documentos} == {"legal", "technical", "additional", "general"}
    assert len(record.criterios_solvencia) == 1 + 1 + 8
    assert [(c.descripcion, c.peso) for c in record.criterios_adjudicacion] == [("PRECIO", 100)]
