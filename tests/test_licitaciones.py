import zipfile
from pathlib import Path

import pytest

from licitaciones import CONTRATOS_MENORES, LICITACIONES, list_files, process_zip_files

FIXTURES = Path(__file__).parent / "fixtures"


def test_annual_range_returns_one_file_per_year():
    files = list_files("201401", "201612", LICITACIONES)

    assert [f.year for f in files] == [2014, 2015, 2016]
    assert all(f.month is None for f in files)
    assert files[0].name == "licitacionesPerfilesContratanteCompleto3_2014.zip"
    assert files[0].url == (
        "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/"
        "licitacionesPerfilesContratanteCompleto3_2014.zip"
    )


def test_monthly_range_within_a_single_year_returns_one_file_per_month():
    files = list_files("202503", "202506", LICITACIONES)

    assert [(f.year, f.month) for f in files] == [
        (2025, 3),
        (2025, 4),
        (2025, 5),
        (2025, 6),
    ]
    assert files[0].name == "licitacionesPerfilesContratanteCompleto3_202503.zip"


def test_from_year_before_start_year_is_clamped():
    files = list_files("200501", "201212", LICITACIONES)

    assert [f.year for f in files] == [2012]


def test_range_crossing_the_monthly_since_boundary():
    files = list_files("202411", "202502", LICITACIONES)

    assert [(f.year, f.month) for f in files] == [
        (2024, None),
        (2025, 1),
        (2025, 2),
    ]



def test_contratos_menores_annual_range_uses_menores_feed():
    files = list_files("202301", "202412", CONTRATOS_MENORES)

    assert [f.year for f in files] == [2023, 2024]
    assert files[0].name == "contratosMenoresPerfilesContratantes_2023.zip"
    assert files[0].url == (
        "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_1143/"
        "contratosMenoresPerfilesContratantes_2023.zip"
    )


def test_contratos_menores_monthly_files_from_2025():
    files = list_files("202512", "202601", CONTRATOS_MENORES)

    assert [f.name for f in files] == [
        "contratosMenoresPerfilesContratantes_202512.zip",
        "contratosMenoresPerfilesContratantes_202601.zip",
    ]


def test_contratos_menores_from_year_before_2018_is_clamped():
    files = list_files("201201", "201812", CONTRATOS_MENORES)

    assert [f.year for f in files] == [2018]

def _build_sample_zip(destination: Path) -> Path:
    with zipfile.ZipFile(destination, "w") as zf:
        zf.write(FIXTURES / "sample_feed.atom", arcname="sample_feed.atom")
    return destination


def test_process_zip_files_writes_one_jsonl_per_zip(tmp_path):
    zip_path = _build_sample_zip(tmp_path / "licitacionesPerfilesContratanteCompleto3_202601.zip")
    output_dir = tmp_path / "parsed"

    output_files = process_zip_files([zip_path], output_dir)

    expected_output = output_dir / "licitacionesPerfilesContratanteCompleto3_202601.jsonl"
    assert output_files == [expected_output]
    lines = expected_output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_process_zip_files_skips_existing_output_by_default(tmp_path):
    zip_path = _build_sample_zip(tmp_path / "a.zip")
    output_dir = tmp_path / "parsed"
    output_dir.mkdir()
    existing_output = output_dir / "a.jsonl"
    existing_output.write_text("sentinel\n", encoding="utf-8")

    output_files = process_zip_files([zip_path], output_dir)

    assert output_files == [existing_output]
    assert existing_output.read_text(encoding="utf-8") == "sentinel\n"


def test_process_zip_files_overwrites_when_requested(tmp_path):
    zip_path = _build_sample_zip(tmp_path / "a.zip")
    output_dir = tmp_path / "parsed"
    output_dir.mkdir()
    existing_output = output_dir / "a.jsonl"
    existing_output.write_text("sentinel\n", encoding="utf-8")

    output_files = process_zip_files([zip_path], output_dir, overwrite=True)

    assert output_files == [existing_output]
    assert existing_output.read_text(encoding="utf-8") != "sentinel\n"


def test_process_zip_files_leaves_no_output_when_parsing_fails(tmp_path):
    bad_zip = tmp_path / "bad.zip"
    bad_zip.write_bytes(b"<html>not a zip</html>")
    output_dir = tmp_path / "parsed"

    with pytest.raises(zipfile.BadZipFile):
        process_zip_files([bad_zip], output_dir)

    assert list(output_dir.iterdir()) == []
