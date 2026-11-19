"""
Funciones recursivas del ETL.

Todas tienen un límite de profundidad explícito (`max_depth`) para que una entrada
maliciosa o mal formada no agote la pila (RecursionError / denegación de servicio).

    flatten_dict               Aplana JSON anidado:  {"a": {"b": 1}} -> {"a_b": 1}
    remove_outliers_zscore     Elimina atípicos por z-score de forma iterativa-recursiva
    median_split_breakpoints   Segmenta valores en 2^depth grupos por medianas sucesivas
    assign_segment             Ubica un valor en su segmento (búsqueda binaria recursiva)
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from etl.domain import DataValidationError

DEFAULT_MAX_DEPTH = 20


# --------------------------------------------------------------------------- JSON
def flatten_dict(
    data: Mapping[str, Any],
    parent_key: str = "",
    sep: str = "_",
    depth: int = 0,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> dict[str, Any]:
    """
    Aplana un diccionario anidado recursivamente.

    Caso base: el valor no es un diccionario -> se agrega tal cual.
    Caso recursivo: el valor es un diccionario -> se aplana con la clave como prefijo.
    Las listas se conservan como valor (no se expanden) para no multiplicar filas.
    """
    if depth > max_depth:
        raise DataValidationError(f"JSON demasiado anidado (profundidad > {max_depth})")

    items: dict[str, Any] = {}
    for key, value in data.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else str(key)
        if isinstance(value, Mapping):
            items.update(flatten_dict(value, new_key, sep, depth + 1, max_depth))
        else:
            items[new_key] = value
    return items


# ----------------------------------------------------------------------- atípicos
def remove_outliers_zscore(
    df: pd.DataFrame,
    column: str,
    threshold: float = 3.0,
    depth: int = 0,
    max_depth: int = 10,
    min_rows: int = 10,
) -> pd.DataFrame:
    """
    Elimina atípicos con z-score de forma recursiva.

    Al quitar los atípicos más extremos, la media y la desviación cambian y pueden
    aparecer nuevos atípicos "enmascarados"; por eso se repite sobre el resultado.

    Casos base: sin atípicos, desviación 0, pocas filas o profundidad máxima alcanzada.
    """
    values = df[column]
    std = values.std(ddof=0)
    if depth >= max_depth or len(df) <= min_rows or not np.isfinite(std) or std == 0:
        return df

    z = (values - values.mean()) / std
    mask = z.abs() <= threshold
    if mask.all():
        return df
    return remove_outliers_zscore(df.loc[mask], column, threshold, depth + 1, max_depth, min_rows)


# --------------------------------------------------------------------- segmentos
def median_split_breakpoints(
    values: Sequence[float] | np.ndarray,
    depth: int,
    max_depth: int = 8,
) -> list[float]:
    """
    Calcula puntos de corte dividiendo recursivamente por la mediana.

    depth=1 -> 1 corte (2 grupos), depth=2 -> 3 cortes (cuartiles aprox.), etc.
    Caso base: depth == 0 o no hay valores suficientes para dividir.
    """
    if depth > max_depth:
        raise DataValidationError(f"depth máximo permitido: {max_depth}")

    arr = np.sort(np.asarray(values, dtype=float))
    arr = arr[np.isfinite(arr)]
    if depth == 0 or arr.size < 2:
        return []

    median = float(np.median(arr))
    lower = arr[arr <= median]
    upper = arr[arr > median]
    return [
        *median_split_breakpoints(lower, depth - 1, max_depth),
        median,
        *median_split_breakpoints(upper, depth - 1, max_depth),
    ]


def assign_segment(value: float, breakpoints: Sequence[float], lo: int = 0, hi: int | None = None) -> int:
    """
    Devuelve el índice de segmento (0..len(breakpoints)) mediante búsqueda binaria recursiva.
    La profundidad está acotada por log2(len(breakpoints)), así que es segura.
    """
    if hi is None:
        hi = len(breakpoints)
    if lo >= hi:
        return lo
    mid = (lo + hi) // 2
    if value <= breakpoints[mid]:
        return assign_segment(value, breakpoints, lo, mid)
    return assign_segment(value, breakpoints, mid + 1, hi)
