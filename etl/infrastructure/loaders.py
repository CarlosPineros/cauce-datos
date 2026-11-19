"""
Carga en PostgreSQL (implementa `DataLoader`).

Seguridad contra SQL injection:
- Esquema, tabla y columnas se validan con `validate_identifier` (lista blanca regex)
  y además se componen con `psycopg.sql.Identifier` (escapado del driver).
- Los tipos SQL salen de un mapeo fijo, nunca del contenido de los datos.
- Los valores viajan por COPY (protocolo binario/texto del driver), nunca
  concatenados en el SQL.
- Todo ocurre en una transacción: si falla, se revierte (sin tablas a medias).
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime
from typing import Any, Literal

import numpy as np
import pandas as pd
from psycopg import sql

from connections.postgres import PostgresClient
from etl.domain import DataLoader, LoadError, validate_identifier

logger = logging.getLogger(__name__)

LoadMode = Literal["replace", "append"]


def sql_type(series: pd.Series) -> str:
    dtype = series.dtype
    if pd.api.types.is_bool_dtype(dtype):
        return "BOOLEAN"
    if pd.api.types.is_integer_dtype(dtype):
        return "BIGINT"
    if pd.api.types.is_float_dtype(dtype):
        return "DOUBLE PRECISION"
    if isinstance(dtype, pd.DatetimeTZDtype):
        return "TIMESTAMPTZ"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "TIMESTAMP"
    non_null = series.dropna()
    if pd.api.types.is_object_dtype(dtype) and len(non_null) and non_null.map(lambda v: isinstance(v, datetime)).all():
        return "TIMESTAMPTZ"
    return "TEXT"


def _to_python(value: Any) -> Any:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, np.generic):
        return value.item()
    return value


def iter_rows(df: pd.DataFrame, text_columns: set[str]) -> Iterator[tuple[Any, ...]]:
    for row in df.itertuples(index=False, name=None):
        out = []
        for col, value in zip(df.columns, row, strict=True):
            v = _to_python(value)
            if v is not None and col in text_columns and not isinstance(v, str):
                v = str(v)
            out.append(v)
        yield tuple(out)


class PostgresLoader(DataLoader):
    def __init__(self, db: PostgresClient, schema: str = "public", mode: LoadMode = "replace") -> None:
        if mode not in ("replace", "append"):
            raise ValueError("mode debe ser 'replace' o 'append'")
        self.db = db
        self.schema = validate_identifier(schema)
        self.mode = mode

    def load(self, df: pd.DataFrame, target: str) -> int:
        table = validate_identifier(target)
        columns = [validate_identifier(str(c)) for c in df.columns]
        types = {c: sql_type(df[c]) for c in columns}
        text_cols = {c for c, t in types.items() if t == "TEXT"}
        qualified = sql.Identifier(self.schema, table)

        try:
            with self.db.transaction() as cur:
                if self.schema != "public":
                    cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(self.schema)))
                if self.mode == "replace":
                    cur.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(qualified))
                cur.execute(
                    sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(
                        qualified,
                        sql.SQL(", ").join(
                            sql.SQL("{} {}").format(sql.Identifier(c), sql.SQL(types[c]))  # tipo de lista fija
                            for c in columns
                        ),
                    )
                )
                copy_stmt = sql.SQL("COPY {} ({}) FROM STDIN").format(
                    qualified, sql.SQL(", ").join(map(sql.Identifier, columns))
                )
                with cur.copy(copy_stmt) as copy:
                    for row in iter_rows(df[columns], text_cols):
                        copy.write_row(row)
        except Exception as exc:
            raise LoadError(f"No se pudo cargar {self.schema}.{table}: {type(exc).__name__}: {exc}") from exc

        logger.info("Cargadas %d filas en %s.%s (%s)", len(df), self.schema, table, self.mode)
        return len(df)
