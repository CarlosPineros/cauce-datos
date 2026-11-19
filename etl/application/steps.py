"""
Pasos concretos del pipeline. Cada uno envuelve UN servicio (SRP) que recibe por
constructor (inyección de dependencias), y se comunica solo por el contexto.

    extraer ─► limpiar ─► transformar ─┬─► describir ──┐
                                       └─► modelar ────┴─► cargar
"""
from __future__ import annotations

import logging
from collections.abc import Mapping

import pandas as pd

from etl.domain import DataExtractor, DataLoader, PipelineContext, PipelineStep

from .cleaning import DataCleaner
from .descriptive import DescriptiveAnalyzer
from .math_model import LinearRegressionModel
from .reporting import ResultMapper
from .transformation import FeatureTransformer

logger = logging.getLogger(__name__)

# Nombres de artefactos en el contexto (contrato entre pasos)
RAW = "raw"
CLEAN = "clean"
CLEANING_REPORT = "cleaning_report"
TRANSFORMED = "transformed"
DESCRIPTIVE = "descriptive_report"
REGRESSION = "regression_result"
SCORED = "scored"
LOADED = "loaded_rows"


class ExtractStep(PipelineStep):
    name = "extraer"

    def __init__(self, extractor: DataExtractor) -> None:
        self.extractor = extractor

    def run(self, context: PipelineContext) -> None:
        df = self.extractor.extract()
        logger.info("Extraídas %d filas, %d columnas", len(df), len(df.columns))
        context.put(RAW, df)


class CleanStep(PipelineStep):
    name = "limpiar"
    depends_on = ("extraer",)

    def __init__(self, cleaner: DataCleaner) -> None:
        self.cleaner = cleaner

    def run(self, context: PipelineContext) -> None:
        df, report = self.cleaner.clean(context.get(RAW))
        context.put(CLEAN, df)
        context.put(CLEANING_REPORT, report)


class TransformStep(PipelineStep):
    name = "transformar"
    depends_on = ("limpiar",)

    def __init__(self, transformer: FeatureTransformer) -> None:
        self.transformer = transformer

    def run(self, context: PipelineContext) -> None:
        context.put(TRANSFORMED, self.transformer.transform(context.get(CLEAN)))


class DescriptiveStep(PipelineStep):
    name = "describir"
    depends_on = ("transformar",)

    def __init__(self, analyzer: DescriptiveAnalyzer) -> None:
        self.analyzer = analyzer

    def run(self, context: PipelineContext) -> None:
        context.put(DESCRIPTIVE, self.analyzer.analyze(context.get(TRANSFORMED)))


class RegressionStep(PipelineStep):
    name = "modelar"
    depends_on = ("transformar",)

    def __init__(self, model: LinearRegressionModel) -> None:
        self.model = model

    def run(self, context: PipelineContext) -> None:
        df = context.get(TRANSFORMED)
        result = self.model.fit(df)
        logger.info("Modelo: %s | R²=%.4f RMSE=%.2f", result.equation(), result.r2, result.rmse)
        context.put(REGRESSION, result)
        context.put(SCORED, self.model.score_frame(df))


class LoadStep(PipelineStep):
    """
    Persiste los artefactos. `tables` mapea nombre lógico -> nombre de tabla destino:
        datos, estadisticas, correlaciones, grupos, modelo, limpieza
    `history_loader` (append) guarda el histórico del modelo y la limpieza.
    """

    name = "cargar"
    depends_on = ("describir", "modelar")

    def __init__(self, loader: DataLoader, history_loader: DataLoader, tables: Mapping[str, str]) -> None:
        self.loader = loader
        self.history_loader = history_loader
        self.tables = dict(tables)

    def run(self, context: PipelineContext) -> None:
        run_id: str = context.get("run_id")
        desc = context.get(DESCRIPTIVE)
        frames: list[tuple[DataLoader, str, pd.DataFrame]] = [
            (self.loader, "datos", context.get(SCORED)),
            (self.loader, "estadisticas", ResultMapper.column_stats(desc, run_id)),
            (self.loader, "correlaciones", ResultMapper.correlations(desc, run_id)),
            (self.loader, "grupos", ResultMapper.group_stats(desc, run_id)),
            (self.history_loader, "modelo", ResultMapper.regression(context.get(REGRESSION), run_id)),
            (self.history_loader, "limpieza", ResultMapper.cleaning(context.get(CLEANING_REPORT), run_id)),
        ]
        loaded: dict[str, int] = {}
        for loader, key, df in frames:
            table = self.tables.get(key)
            if not table or df.empty:
                continue
            loaded[table] = loader.load(df, table)
        logger.info("Filas cargadas: %s", loaded)
        context.put(LOADED, loaded)
