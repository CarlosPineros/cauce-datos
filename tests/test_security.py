"""Pruebas de las defensas de seguridad: SQL injection, path traversal, tamaños y formatos."""
import pandas as pd
import pytest

from etl.domain import UnsafeInputError, validate_identifier, validate_object_key
from etl.infrastructure import LocalFileExtractor
from etl.infrastructure.loaders import PostgresLoader, iter_rows, sql_type
from etl.infrastructure.parsers import detect_format, parse_bytes


@pytest.mark.parametrize("name", ["ventas", "_tmp", "tabla_2026", "a" * 63])
def test_identificadores_validos(name):
    assert validate_identifier(name) == name


@pytest.mark.parametrize(
    "name",
    ['ventas"; DROP TABLE x; --', "Ventas", "1tabla", "a b", "", "a" * 64, "esq.tabla", None],
)
def test_identificadores_maliciosos(name):
    with pytest.raises(UnsafeInputError):
        validate_identifier(name)


@pytest.mark.parametrize("key", ["../secreto.json", "/etc/passwd", "a/../../b.csv", "a\\b.csv", "a b.csv", ""])
def test_claves_maliciosas(key):
    with pytest.raises(UnsafeInputError):
        validate_object_key(key)


def test_path_traversal_local(tmp_path):
    with pytest.raises(UnsafeInputError):
        LocalFileExtractor(tmp_path, "../fuera.csv")


def test_limite_de_tamano_local(tmp_path):
    (tmp_path / "grande.csv").write_bytes(b"a\n" + b"1\n" * 1000)
    with pytest.raises(UnsafeInputError, match="límite"):
        LocalFileExtractor(tmp_path, "grande.csv", max_bytes=100).extract()


def test_lectura_local_valida(tmp_path):
    (tmp_path / "ok.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    df = LocalFileExtractor(tmp_path, "ok.csv").extract()
    assert df.to_dict("records") == [{"a": 1, "b": 2}]


@pytest.mark.parametrize("name", ["datos.pkl", "datos.pickle", "datos.yaml", "datos.exe", "sin_extension"])
def test_formatos_no_permitidos(name):
    with pytest.raises(UnsafeInputError):
        detect_format(name)


def test_json_debe_ser_lista_de_objetos():
    from etl.domain import DataValidationError

    with pytest.raises(DataValidationError):
        parse_bytes(b"[1, 2, 3]", "json")


def test_loader_rechaza_columnas_maliciosas():
    loader = PostgresLoader(db=None, schema="etl")  # no llega a usar la BD
    df = pd.DataFrame({'x"; DROP TABLE t; --': [1]})
    with pytest.raises(UnsafeInputError):
        loader.load(df, "tabla")


def test_loader_rechaza_tabla_maliciosa():
    with pytest.raises(UnsafeInputError):
        PostgresLoader(db=None).load(pd.DataFrame({"a": [1]}), "t; DROP DATABASE prueba")


def test_loader_rechaza_esquema_malicioso():
    with pytest.raises(UnsafeInputError):
        PostgresLoader(db=None, schema="public; --")


def test_tipos_sql_de_lista_fija():
    df = pd.DataFrame({
        "i": [1], "f": [1.5], "b": [True], "s": ["x"],
        "t": pd.to_datetime(["2025-01-01"], utc=True),
    })
    assert {c: sql_type(df[c]) for c in df} == {
        "i": "BIGINT", "f": "DOUBLE PRECISION", "b": "BOOLEAN", "s": "TEXT", "t": "TIMESTAMPTZ",
    }


def test_iter_rows_convierte_nulos_y_numpy():
    df = pd.DataFrame({"a": [1.0, float("nan")], "b": ["x", None]})
    rows = list(iter_rows(df, {"b"}))
    assert rows == [(1.0, "x"), (None, None)]
    assert type(rows[0][0]) is float
