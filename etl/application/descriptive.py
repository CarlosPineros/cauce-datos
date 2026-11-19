"""
Modelo descriptivo: medidas de tendencia central, dispersión, forma, correlación
y agregados por grupo.
"""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from etl.domain import DataValidationError, DescriptiveReport


def _f(value: float) -> float:
    """Convierte a float nativo y reemplaza NaN/inf por NaN estable (serializable)."""
    v = float(value)
    return v if np.isfinite(v) else float("nan")


class DescriptiveAnalyzer:
    def __init__(
        self,
        numeric_columns: Sequence[str],
        group_by: str | None = None,
        value_column: str | None = None,
    ) -> None:
        self.numeric_columns = tuple(numeric_columns)
        self.group_by = group_by
        self.value_column = value_column

    def analyze(self, df: pd.DataFrame) -> DescriptiveReport:
        missing = [c for c in self.numeric_columns if c not in df.columns]
        if missing:
            raise DataValidationError(f"Columnas no encontradas para el análisis: {missing}")

        return DescriptiveReport(
            row_count=len(df),
            column_stats={c: self.column_stats(df[c]) for c in self.numeric_columns},
            correlations=self._correlations(df),
            group_stats=self._group_stats(df),
        )

    @staticmethod
    def column_stats(s: pd.Series) -> dict[str, float]:
        s = s.dropna().astype(float)
        mean = s.mean()
        q1, median, q3 = s.quantile([0.25, 0.5, 0.75])
        std = s.std(ddof=1)
        return {
            "n": _f(s.count()),
            "media": _f(mean),
            "mediana": _f(median),
            "moda": _f(s.mode().iloc[0]) if not s.mode().empty else float("nan"),
            "desv_std": _f(std),
            "varianza": _f(s.var(ddof=1)),
            "min": _f(s.min()),
            "q1": _f(q1),
            "q3": _f(q3),
            "max": _f(s.max()),
            "rango": _f(s.max() - s.min()),
            "iqr": _f(q3 - q1),
            "coef_variacion": _f(std / mean) if mean else float("nan"),
            "asimetria": _f(s.skew()),
            "curtosis": _f(s.kurt()),
        }

    def _correlations(self, df: pd.DataFrame) -> dict[str, dict[str, float]]:
        corr = df[list(self.numeric_columns)].corr(method="pearson")
        return {r: {c: _f(corr.loc[r, c]) for c in corr.columns} for r in corr.index}

    def _group_stats(self, df: pd.DataFrame) -> list[dict]:
        if not self.group_by or not self.value_column:
            return []
        g = df.groupby(self.group_by, observed=True)[self.value_column]
        out = g.agg(["count", "sum", "mean", "median", "std", "min", "max"]).reset_index()
        total = out["sum"].sum()
        out["participacion"] = out["sum"] / total if total else 0.0
        out = out.sort_values("sum", ascending=False)
        return [
            {k: (_f(v) if isinstance(v, (int, float, np.number)) else str(v)) for k, v in row.items()}
            for row in out.to_dict(orient="records")
        ]
