import pandas as pd
import pytest

from etl.application import DataCleaner, normalize_column_name
from etl.domain import DataValidationError
from etl.infrastructure.parsers import records_to_frame
from etl.presentation.ventas_pipeline import VENTAS_CLEANING


@pytest.fixture
def cleaned(ventas_records):
    return DataCleaner(VENTAS_CLEANING).clean(records_to_frame(ventas_records))


def test_reporte_de_limpieza(cleaned):
    df, report = cleaned
    assert report.rows_in == 65
    assert report.duplicates_removed == 1
    assert report.out_of_range_removed == 1
    assert report.missing_required_removed == 1
    assert report.values_imputed >= 1
    assert report.rows_out == len(df)


def test_normaliza_categorias(cleaned):
    df, _ = cleaned
    assert set(df["ubicacion_region"]) == {"norte", "sur"}


def test_sin_nulos_ni_negativos(cleaned):
    df, _ = cleaned
    assert not df[["cantidad", "precio_unitario", "gasto_publicidad"]].isna().any().any()
    assert (df["cantidad"] >= 0).all()


def test_falla_si_faltan_columnas():
    with pytest.raises(DataValidationError, match="Faltan columnas"):
        DataCleaner(VENTAS_CLEANING).clean(pd.DataFrame({"x": [1]}))


def test_falla_si_esta_vacio():
    with pytest.raises(DataValidationError):
        DataCleaner(VENTAS_CLEANING).clean(pd.DataFrame())


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Precio Unitario (€)", "precio_unitario"),
        ("  Año ", "ano"),
        ("1col", "col_1col"),
        ('x"; DROP TABLE t; --', "x_drop_table_t"),
    ],
)
def test_normalize_column_name(raw, expected):
    assert normalize_column_name(raw) == expected
