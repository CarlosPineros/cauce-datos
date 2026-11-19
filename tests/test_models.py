import numpy as np
import pandas as pd
import pytest

from etl.application import DescriptiveAnalyzer, LinearRegressionModel
from etl.domain import DataValidationError


@pytest.fixture
def lineal():
    rng = np.random.default_rng(0)
    x1 = rng.uniform(0, 100, 500)
    x2 = rng.uniform(0, 10, 500)
    y = 3.0 + 2.0 * x1 - 5.0 * x2 + rng.normal(0, 0.01, 500)
    return pd.DataFrame({"x1": x1, "x2": x2, "y": y})


class TestRegresion:
    def test_recupera_coeficientes(self, lineal):
        r = LinearRegressionModel("y", ["x1", "x2"]).fit(lineal)
        assert r.intercept == pytest.approx(3.0, abs=0.01)
        assert r.coefficients["x1"] == pytest.approx(2.0, abs=1e-3)
        assert r.coefficients["x2"] == pytest.approx(-5.0, abs=1e-3)
        assert r.r2 > 0.9999

    def test_score_frame_agrega_prediccion_y_residuo(self, lineal):
        model = LinearRegressionModel("y", ["x1", "x2"])
        model.fit(lineal)
        scored = model.score_frame(lineal)
        assert {"pred_y", "residuo_y"} <= set(scored.columns)
        assert scored["residuo_y"].abs().max() < 0.1

    def test_detecta_colinealidad(self, lineal):
        lineal["x3"] = lineal["x1"] * 2
        with pytest.raises(DataValidationError, match="colineales"):
            LinearRegressionModel("y", ["x1", "x3"]).fit(lineal)

    def test_pocas_observaciones(self):
        with pytest.raises(DataValidationError):
            LinearRegressionModel("y", ["x"]).fit(pd.DataFrame({"x": [1.0, 2.0], "y": [1.0, 2.0]}))

    def test_rechaza_nan(self, lineal):
        lineal.loc[0, "x1"] = np.nan
        with pytest.raises(DataValidationError, match="NaN"):
            LinearRegressionModel("y", ["x1"]).fit(lineal)

    def test_predict_sin_entrenar(self, lineal):
        with pytest.raises(RuntimeError):
            LinearRegressionModel("y", ["x1"]).predict(lineal)


class TestDescriptivo:
    def test_estadisticas_basicas(self):
        df = pd.DataFrame({"v": [1.0, 2.0, 3.0, 4.0, 5.0], "g": ["a", "a", "b", "b", "b"]})
        rep = DescriptiveAnalyzer(["v"], group_by="g", value_column="v").analyze(df)
        s = rep.column_stats["v"]
        assert s["media"] == 3.0
        assert s["mediana"] == 3.0
        assert s["min"] == 1.0 and s["max"] == 5.0
        assert s["iqr"] == 2.0
        assert rep.row_count == 5
        assert [g["g"] for g in rep.group_stats] == ["b", "a"]
        assert sum(g["participacion"] for g in rep.group_stats) == pytest.approx(1.0)

    def test_correlacion_perfecta(self):
        df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [2.0, 4.0, 6.0]})
        rep = DescriptiveAnalyzer(["a", "b"]).analyze(df)
        assert rep.correlations["a"]["b"] == pytest.approx(1.0)
