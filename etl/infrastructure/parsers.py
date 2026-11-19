"""
Conversión de bytes -> DataFrame. Formatos soportados: csv, json, jsonl.

Seguridad: solo formatos de datos (sin pickle, sin eval, sin YAML inseguro).
El JSON anidado se aplana con la función recursiva `flatten_dict`, que tiene
límite de profundidad.
"""
from __future__ import annotations

import io
import json
from typing import Any

import pandas as pd

from etl.application.recursion import flatten_dict
from etl.domain import DataValidationError, UnsafeInputError

SUPPORTED_FORMATS = ("csv", "json", "jsonl")


def detect_format(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in SUPPORTED_FORMATS:
        raise UnsafeInputError(f"Formato no soportado: '{ext}'. Permitidos: {SUPPORTED_FORMATS}")
    return ext


def parse_bytes(data: bytes, fmt: str, encoding: str = "utf-8") -> pd.DataFrame:
    if fmt == "csv":
        return pd.read_csv(io.BytesIO(data), encoding=encoding)
    text = data.decode(encoding)
    if fmt == "json":
        return records_to_frame(_json_records(json.loads(text)))
    if fmt == "jsonl":
        return records_to_frame([json.loads(line) for line in text.splitlines() if line.strip()])
    raise UnsafeInputError(f"Formato no soportado: {fmt!r}")


def _json_records(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        return payload["records"]
    raise DataValidationError("El JSON debe ser una lista de objetos o {'records': [...]}")


def records_to_frame(records: list[Any]) -> pd.DataFrame:
    if not all(isinstance(r, dict) for r in records):
        raise DataValidationError("Todos los registros JSON deben ser objetos")
    return pd.DataFrame([flatten_dict(r) for r in records])
