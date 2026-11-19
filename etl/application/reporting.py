"""Convierte los resultados de los modelos a DataFrames tabulares para persistirlos."""
from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from etl.domain import DescriptiveReport, RegressionResult

from .cleaning import CleaningReport


class ResultMapper:
    @staticmethod
    def column_stats(report: DescriptiveReport, run_id: str) -> pd.DataFrame:
        rows = [{"run_id": run_id, "variable": col, **stats} for col, stats in report.column_stats.items()]
        return pd.DataFrame(rows)

    @staticmethod
    def correlations(report: DescriptiveReport, run_id: str) -> pd.DataFrame:
        rows = [
            {"run_id": run_id, "variable_a": a, "variable_b": b, "pearson": v}
            for a, row in report.correlations.items()
            for b, v in row.items()
            if a < b  # solo el triángulo superior, sin diagonal
        ]
        return pd.DataFrame(rows)

    @staticmethod
    def group_stats(report: DescriptiveReport, run_id: str) -> pd.DataFrame:
        return pd.DataFrame([{"run_id": run_id, **row} for row in report.group_stats])

    @staticmethod
    def regression(result: RegressionResult, run_id: str) -> pd.DataFrame:
        now = datetime.now(UTC)
        base = {
            "run_id": run_id,
            "ejecutado_en": now,
            "objetivo": result.target,
            "r2": result.r2,
            "r2_ajustado": result.adj_r2,
            "rmse": result.rmse,
            "mae": result.mae,
            "n_obs": result.n_obs,
            "ecuacion": result.equation(),
        }
        terms = {"intercepto": result.intercept, **result.coefficients}
        return pd.DataFrame([{**base, "termino": t, "coeficiente": c} for t, c in terms.items()])

    @staticmethod
    def cleaning(report: CleaningReport, run_id: str) -> pd.DataFrame:
        return pd.DataFrame([{"run_id": run_id, "ejecutado_en": datetime.now(UTC), **report.as_dict()}])
