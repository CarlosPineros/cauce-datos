"""Extractores concretos (implementan `DataExtractor`)."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from connections.s3 import S3Client
from etl.domain import DataExtractor, ExtractionError, UnsafeInputError, validate_object_key

from .parsers import detect_format, parse_bytes

logger = logging.getLogger(__name__)

DEFAULT_MAX_BYTES = 50 * 1024 * 1024  # 50 MB


class S3ObjectExtractor(DataExtractor):
    def __init__(self, s3: S3Client, key: str, max_bytes: int = DEFAULT_MAX_BYTES, fmt: str | None = None) -> None:
        self.s3 = s3
        self.key = validate_object_key(key)
        self.fmt = fmt or detect_format(key)
        self.max_bytes = max_bytes

    def extract(self) -> pd.DataFrame:
        try:
            data = self.s3.get_object(self.key, max_bytes=self.max_bytes)
        except ValueError as exc:
            raise UnsafeInputError(str(exc)) from exc
        except Exception as exc:
            raise ExtractionError(f"No se pudo leer s3://{self.s3.bucket}/{self.key}: {exc}") from exc
        logger.info("Leídos %d bytes de s3://%s/%s", len(data), self.s3.bucket, self.key)
        return parse_bytes(data, self.fmt)


class LocalFileExtractor(DataExtractor):
    """Lee un archivo local restringido a `base_dir` (evita path traversal)."""

    def __init__(self, base_dir: str | Path, relative_path: str, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
        self.base_dir = Path(base_dir).resolve()
        validate_object_key(relative_path)
        self.path = (self.base_dir / relative_path).resolve()
        if not self.path.is_relative_to(self.base_dir):
            raise UnsafeInputError(f"Ruta fuera del directorio permitido: {relative_path!r}")
        self.fmt = detect_format(self.path.name)
        self.max_bytes = max_bytes

    def extract(self) -> pd.DataFrame:
        if not self.path.is_file():
            raise ExtractionError(f"Archivo no encontrado: {self.path.name}")
        with self.path.open("rb") as fh:
            data = fh.read(self.max_bytes + 1)
        if len(data) > self.max_bytes:
            raise UnsafeInputError(f"Archivo excede el límite de {self.max_bytes} bytes")
        return parse_bytes(data, self.fmt)
