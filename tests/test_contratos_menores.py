from contratos_menores import list_files


def test_annual_range_uses_menores_feed():
    files = list_files("202301", "202412")

    assert [f.year for f in files] == [2023, 2024]
    assert files[0].name == "contratosMenoresPerfilesContratantes_2023.zip"
    assert files[0].url == (
        "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_1143/"
        "contratosMenoresPerfilesContratantes_2023.zip"
    )


def test_monthly_files_from_2025():
    files = list_files("202512", "202601")

    assert [f.name for f in files] == [
        "contratosMenoresPerfilesContratantes_202512.zip",
        "contratosMenoresPerfilesContratantes_202601.zip",
    ]


def test_from_year_before_2018_is_clamped():
    files = list_files("201201", "201812")

    assert [f.year for f in files] == [2018]
