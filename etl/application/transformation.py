"""
Transformaciones / ingeniería de variables (SRP).

Patrón estrategia: cada transformación implementa `FeatureTransform` y el
`FeatureTransformer` las aplica en orden. Agregar una nueva no exige modificar
las existentes (OCP).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

import numpy as np
import pandas as pd

from etl.domain import DataValidationError

from .recursion import assign_segment, median_split_breakpoints


class FeatureTransform(ABC):
    @abstractmethod
    def apply(self, df: pd.DataFrame) -> pd.DataFrame: ...


class RevenueFeatures(FeatureTransform):
    """ingreso_bruto = cantidad · precio ;  ingreso_neto = bruto · (1 − descuento)."""

    def __init__(self, qty: str = "cantidad", price: str = "precio_unitario", discount: str = "descuento") -> None:
        self.qty, self.price, self.discount = qty, price, discount

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["ingreso_bruto"] = df[self.qty] * df[self.price]
        df["ingreso_neto"] = df["ingreso_bruto"] * (1.0 - df[self.discount])
        return df


class DateFeatures(FeatureTransform):
    def __init__(self, column: str = "fecha") -> None:
        self.column = column

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        dt = df[self.column].dt
        df["anio"] = dt.year.astype("int64")
        df["mes"] = dt.month.astype("int64")
        df["trimestre"] = dt.quarter.astype("int64")
        df["dia_semana"] = dt.day_of_week.astype("int64")
        return df


class LogTransform(FeatureTransform):
    """log(1 + x): reduce la asimetría de variables monetarias. Requiere x ≥ 0."""

    def __init__(self, columns: Sequence[str]) -> None:
        self.columns = tuple(columns)

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        for col in self.columns:
            if (df[col] < 0).any():
                raise DataValidationError(f"log1p requiere valores ≥ 0 en '{col}'")
            df[f"log_{col}"] = np.log1p(df[col])
        return df


class ZScoreScaler(FeatureTransform):
    """z = (x − μ) / σ. Si σ = 0 la columna resultante es 0."""

    def __init__(self, columns: Sequence[str]) -> None:
        self.columns = tuple(columns)

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        for col in self.columns:
            std = df[col].std(ddof=0)
            df[f"z_{col}"] = 0.0 if not std else (df[col] - df[col].mean()) / std
        return df


class MedianSegmenter(FeatureTransform):
    """Segmenta una variable en 2^depth grupos usando cortes recursivos por mediana."""

    def __init__(self, column: str, depth: int = 2, output: str | None = None) -> None:
        self.column, self.depth = column, depth
        self.output = output or f"segmento_{column}"

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        breakpoints = median_split_breakpoints(df[self.column].to_numpy(), self.depth)
        df[self.output] = df[self.column].map(lambda v: assign_segment(float(v), breakpoints)).astype("int64")
        return df


class FeatureTransformer:
    def __init__(self, transforms: Sequence[FeatureTransform]) -> None:
        self.transforms = tuple(transforms)

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        for t in self.transforms:
            df = t.apply(df)
        return df
