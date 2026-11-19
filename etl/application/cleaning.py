"""
Limpieza de datos (SRP: solo limpia, no transforma ni modela).

Cada regla es un método pequeño; el orden se define en `clean()`.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field

import pandas as pd

from etl.domain import DataValidationError

from .recursion import remove_outliers_zscore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CleaningConfig:
    key_column: str | None = None
    required_columns: tuple[str, ...] = ()
    numeric_columns: tuple[str, ...] = ()
    date_columns: tuple[str, ...] = ()
    categorical_columns: tuple[str, ...] = ()
    # Rangos válidos (inclusive) por columna numérica: {"descuento": (0, 1)}
    valid_ranges: dict[str, tuple[float | None, float | None]] = field(default_factory=dict)
    outlier_columns: tuple[str, ...] = ()
    outlier_z_threshold: float = 3.0
    unknown_category: str = "desconocido"


@dataclass
class CleaningReport:
    rows_in: int = 0
    rows_out: int = 0
    duplicates_removed: int = 0
    missing_required_removed: int = 0
    out_of_range_removed: int = 0
    outliers_removed: int = 0
    values_imputed: int = 0

    def as_dict(self) -> dict[str, int]:
        return dict(self.__dict__)


def normalize_column_name(name: object) -> str:
    """'Precio Unitario (€)' -> 'precio_unitario'. Garantiza identificadores SQL seguros."""
    text = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    if not text or text[0].isdigit():
        text = f"col_{text}"
    return text[:63]


class DataCleaner:
    def __init__(self, config: CleaningConfig) -> None:
        self.config = config

    def clean(self, df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
        if df.empty:
            raise DataValidationError("El DataFrame de entrada está vacío")

        report = CleaningReport(rows_in=len(df))
        df = self._normalize_columns(df)
        self._check_schema(df)
        df = self._strip_strings(df)
        df = self._coerce_types(df)
        df = self._drop_duplicates(df, report)
        df = self._drop_missing_required(df, report)
        df = self._drop_out_of_range(df, report)
        df = self._impute(df, report)
        df = self._drop_outliers(df, report)

        if df.empty:
            raise DataValidationError("No quedaron filas válidas tras la limpieza")

        report.rows_out = len(df)
        logger.info("Limpieza: %s", report.as_dict())
        return df.reset_index(drop=True), report

    # ------------------------------------------------------------------ reglas
    @staticmethod
    def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        new_cols = [normalize_column_name(c) for c in df.columns]
        if len(set(new_cols)) != len(new_cols):
            raise DataValidationError(f"Columnas duplicadas tras normalizar: {new_cols}")
        return df.set_axis(new_cols, axis=1)

    def _check_schema(self, df: pd.DataFrame) -> None:
        c = self.config
        expected = set(c.required_columns) | set(c.numeric_columns) | set(c.date_columns) | set(c.categorical_columns)
        if c.key_column:
            expected.add(c.key_column)
        missing = expected - set(df.columns)
        if missing:
            raise DataValidationError(f"Faltan columnas requeridas: {sorted(missing)}")

    @staticmethod
    def _strip_strings(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        for col in df.columns:
            if pd.api.types.is_string_dtype(df[col]) or df[col].dtype == object:
                stripped = df[col].map(lambda v: v.strip() if isinstance(v, str) else v)
                df[col] = stripped.replace({"": None, "nan": None, "null": None, "None": None, "N/A": None})
        return df

    def _coerce_types(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        for col in self.config.numeric_columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
        for col in self.config.date_columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
        for col in self.config.categorical_columns:
            df[col] = df[col].map(lambda v: v.lower() if isinstance(v, str) else v)
        return df

    def _drop_duplicates(self, df: pd.DataFrame, report: CleaningReport) -> pd.DataFrame:
        before = len(df)
        df = df.drop_duplicates()
        if self.config.key_column:
            df = df.dropna(subset=[self.config.key_column])
            df = df.drop_duplicates(subset=[self.config.key_column], keep="first")
        report.duplicates_removed = before - len(df)
        return df

    def _drop_missing_required(self, df: pd.DataFrame, report: CleaningReport) -> pd.DataFrame:
        if not self.config.required_columns:
            return df
        before = len(df)
        df = df.dropna(subset=list(self.config.required_columns))
        report.missing_required_removed = before - len(df)
        return df

    def _drop_out_of_range(self, df: pd.DataFrame, report: CleaningReport) -> pd.DataFrame:
        before = len(df)
        for col, (low, high) in self.config.valid_ranges.items():
            valid = df[col].isna()  # los nulos se imputan después, no se descartan aquí
            in_range = pd.Series(True, index=df.index)
            if low is not None:
                in_range &= df[col] >= low
            if high is not None:
                in_range &= df[col] <= high
            df = df.loc[valid | in_range]
        report.out_of_range_removed = before - len(df)
        return df

    def _impute(self, df: pd.DataFrame, report: CleaningReport) -> pd.DataFrame:
        df = df.copy()
        imputed = 0
        for col in self.config.numeric_columns:
            n = int(df[col].isna().sum())
            if n:
                median = df[col].median()
                df[col] = df[col].fillna(0.0 if pd.isna(median) else median)
                imputed += n
        for col in self.config.categorical_columns:
            n = int(df[col].isna().sum())
            if n:
                df[col] = df[col].fillna(self.config.unknown_category)
                imputed += n
        report.values_imputed = imputed
        return df

    def _drop_outliers(self, df: pd.DataFrame, report: CleaningReport) -> pd.DataFrame:
        before = len(df)
        for col in self.config.outlier_columns:
            df = remove_outliers_zscore(df, col, self.config.outlier_z_threshold)
        report.outliers_removed = before - len(df)
        return df
