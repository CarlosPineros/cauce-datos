import numpy as np
import pandas as pd
import pytest

from etl.application.recursion import (
    assign_segment,
    flatten_dict,
    median_split_breakpoints,
    remove_outliers_zscore,
)
from etl.domain import DataValidationError


class TestFlattenDict:
    def test_aplana_niveles_anidados(self):
        assert flatten_dict({"a": 1, "b": {"c": 2, "d": {"e": 3}}}) == {"a": 1, "b_c": 2, "b_d_e": 3}

    def test_conserva_listas_sin_expandir(self):
        assert flatten_dict({"a": [1, 2]}) == {"a": [1, 2]}

    def test_diccionario_vacio(self):
        assert flatten_dict({}) == {}

    def test_rechaza_anidamiento_excesivo(self):
        deep: dict = {}
        node = deep
        for _ in range(50):
            node["x"] = {}
            node = node["x"]
        with pytest.raises(DataValidationError):
            flatten_dict(deep, max_depth=20)


class TestRemoveOutliers:
    def test_elimina_atipicos_enmascarados(self):
        # 1000 enmascara a 200: tras quitar 1000, 200 se vuelve atípico (requiere recursión)
        values = [10.0] * 30 + [11.0] * 30 + [200.0, 1000.0]
        out = remove_outliers_zscore(pd.DataFrame({"v": values}), "v", threshold=3.0)
        assert out["v"].max() == 11.0

    def test_sin_variacion_no_elimina(self):
        df = pd.DataFrame({"v": [5.0] * 20})
        assert len(remove_outliers_zscore(df, "v")) == 20

    def test_respeta_profundidad_maxima(self):
        df = pd.DataFrame({"v": [*np.arange(50.0), 1e6]})
        assert len(remove_outliers_zscore(df, "v", max_depth=0)) == 51


class TestSegmentos:
    def test_depth_2_genera_tres_cortes(self):
        cuts = median_split_breakpoints(np.arange(1, 101), depth=2)
        assert len(cuts) == 3
        assert cuts == sorted(cuts)

    def test_depth_0_sin_cortes(self):
        assert median_split_breakpoints([1, 2, 3], depth=0) == []

    def test_depth_excesivo(self):
        with pytest.raises(DataValidationError):
            median_split_breakpoints([1, 2], depth=99)

    @pytest.mark.parametrize(("value", "expected"), [(0, 0), (25, 0), (26, 1), (60, 2), (99, 3)])
    def test_assign_segment(self, value, expected):
        assert assign_segment(value, [25, 50, 75]) == expected

    def test_segmentos_balanceados(self):
        values = np.arange(1, 1001)
        cuts = median_split_breakpoints(values, depth=2)
        counts = np.bincount([assign_segment(v, cuts) for v in values])
        assert counts.tolist() == [250, 250, 250, 250]
