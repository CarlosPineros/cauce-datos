from __future__ import annotations

import pandas as pd
import pytest

from etl.domain import DataExtractor, DataLoader


class InMemoryExtractor(DataExtractor):
    def __init__(self, df: pd.DataFrame) -> None:
        self.df = df

    def extract(self) -> pd.DataFrame:
        return self.df.copy()


class InMemoryLoader(DataLoader):
    def __init__(self) -> None:
        self.tables: dict[str, list[pd.DataFrame]] = {}

    def load(self, df: pd.DataFrame, target: str) -> int:
        self.tables.setdefault(target, []).append(df.copy())
        return len(df)


@pytest.fixture
def ventas_records() -> list[dict]:
    """Registros anidados con errores conocidos."""
    base = [
        {
            "id_venta": i,
            "fecha": f"2025-0{1 + i % 9}-1{i % 9}",
            "ubicacion": {"region": ["Norte", "Sur"][i % 2], "ciudad": "X"},
            "producto": {"nombre": "Silla", "categoria": "muebles"},
            "cantidad": 10 + (i % 7),
            "precio_unitario": 100.0 + i,
            "descuento": [0, 0.1, 0.2][i % 3],
            "gasto_publicidad": 200.0 + 3 * i,
        }
        for i in range(1, 61)
    ]
    base.append(dict(base[0]))                                              # duplicado
    base.append({**base[1], "id_venta": 900, "cantidad": -5})               # fuera de rango
    base.append({**base[2], "id_venta": 901, "precio_unitario": None})      # requerido nulo
    base.append({**base[3], "id_venta": 902, "gasto_publicidad": None})     # imputable
    base.append({**base[4], "id_venta": 903, "ubicacion": {"region": "  NORTE ", "ciudad": "X"}})
    return base


@pytest.fixture
def in_memory_loader() -> InMemoryLoader:
    return InMemoryLoader()
