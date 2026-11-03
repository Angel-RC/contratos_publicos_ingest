from asturias_2 import list_files


def test_list_files_returns_one_file_per_year():
    files = list_files(2019, 2021)

    assert [f.year for f in files] == [2019, 2020, 2021]
    assert files[0].name == "dataset-contratacion-centralizada-2019.csv"
    assert files[0].url == (
        "https://descargas.asturias.es/asturias/opendata/SectorPublico/contratacion/"
        "dataset-contratacion-centralizada-2019.csv"
    )


def test_list_files_clamps_year_from_to_start_year():
    files = list_files(2015, 2020)

    assert [f.year for f in files] == [2019, 2020]
