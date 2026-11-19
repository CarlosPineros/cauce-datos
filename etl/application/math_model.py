"""
Modelo matemático: regresión lineal múltiple por Mínimos Cuadrados Ordinarios.

    y = β0 + β1·x1 + ... + βk·xk + ε
    β = argmin ‖y − Xβ‖²    (resuelto con descomposición SVD vía numpy.linalg.lstsq,
                             numéricamente más estable que invertir XᵀX)

Métricas:
    R²      = 1 − SS_res / SS_tot
    R²_adj  = 1 − (1 − R²)·(n − 1)/(n − k − 1)
    RMSE    = √(Σ(y − ŷ)² / n)
    MAE     = Σ|y − ŷ| / n
"""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from etl.domain import DataValidationError, RegressionResult


class LinearRegressionModel:
    def __init__(self, target: str, features: Sequence[str]) -> None:
        if not features:
            raise ValueError("Se requiere al menos una variable explicativa")
        self.target = target
        self.features = tuple(features)
        self._beta: np.ndarray | None = None

    # ------------------------------------------------------------- ajuste
    def fit(self, df: pd.DataFrame) -> RegressionResult:
        X, y = self._matrices(df)
        n, k = X.shape[0], len(self.features)
        if n <= k + 1:
            raise DataValidationError(f"Observaciones insuficientes: n={n}, se requieren > {k + 1}")

        beta, _, rank, _ = np.linalg.lstsq(X, y, rcond=None)
        if rank < X.shape[1]:
            raise DataValidationError("Variables explicativas colineales (matriz de rango deficiente)")
        self._beta = beta

        y_hat = X @ beta
        resid = y - y_hat
        ss_res = float(resid @ resid)
        ss_tot = float(((y - y.mean()) ** 2).sum())
        r2 = 1.0 - ss_res / ss_tot if ss_tot else 0.0

        return RegressionResult(
            target=self.target,
            features=self.features,
            intercept=float(beta[0]),
            coefficients={f: float(b) for f, b in zip(self.features, beta[1:], strict=True)},
            r2=r2,
            adj_r2=1.0 - (1.0 - r2) * (n - 1) / (n - k - 1),
            rmse=float(np.sqrt(ss_res / n)),
            mae=float(np.abs(resid).mean()),
            n_obs=n,
        )

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        if self._beta is None:
            raise RuntimeError("El modelo no está entrenado; llama a fit() primero")
        X = self._design_matrix(df)
        return X @ self._beta

    def score_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        """Agrega columnas de predicción y residuo al DataFrame."""
        out = df.copy()
        out[f"pred_{self.target}"] = self.predict(df)
        out[f"residuo_{self.target}"] = out[self.target] - out[f"pred_{self.target}"]
        return out

    # ---------------------------------------------------------- matrices
    def _design_matrix(self, df: pd.DataFrame) -> np.ndarray:
        missing = [c for c in self.features if c not in df.columns]
        if missing:
            raise DataValidationError(f"Variables no encontradas: {missing}")
        X = df[list(self.features)].to_numpy(dtype=float)
        return np.column_stack([np.ones(len(X)), X])

    def _matrices(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        if self.target not in df.columns:
            raise DataValidationError(f"Variable objetivo no encontrada: {self.target}")
        X = self._design_matrix(df)
        y = df[self.target].to_numpy(dtype=float)
        if not (np.isfinite(X).all() and np.isfinite(y).all()):
            raise DataValidationError("Hay valores NaN/inf en las variables del modelo")
        return X, y
