"""
Raíz de composición (composition root) del pipeline de VENTAS.

Es el ÚNICO lugar que conoce las clases concretas y las conecta. Para crear otro
pipeline (clientes, inventario...) se escribe otro módulo como este, sin tocar
las capas de dominio, aplicación ni infraestructura (OCP).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from etl.application import (
    CleaningConfig,
    CleanStep,
    DataCleaner,
    DateFeatures,
    DescriptiveAnalyzer,
    DescriptiveStep,
    ExtractStep,
    FeatureTransformer,
    LinearRegressionModel,
    LoadStep,
    LogTransform,
    MedianSegmenter,
    PipelineOrchestrator,
    RegressionStep,
    RevenueFeatures,
    TransformStep,
    ZScoreScaler,
)
from etl.domain import DataExtractor, DataLoader

NUMERIC = ("cantidad", "precio_unitario", "descuento", "gasto_publicidad")

VENTAS_CLEANING = CleaningConfig(
    key_column="id_venta",
    required_columns=("id_venta", "fecha", "cantidad", "precio_unitario"),
    numeric_columns=NUMERIC,
    date_columns=("fecha",),
    categorical_columns=("ubicacion_region", "ubicacion_ciudad", "producto_nombre", "producto_categoria"),
    valid_ranges={
        "cantidad": (0, None),
        "precio_unitario": (0.01, None),
        "descuento": (0, 1),
        "gasto_publicidad": (0, None),
    },
    outlier_columns=("cantidad", "precio_unitario", "gasto_publicidad"),
    outlier_z_threshold=3.0,
)


@dataclass(frozen=True)
class VentasTables:
    datos: str = "ventas_datos"
    estadisticas: str = "ventas_estadisticas"
    correlaciones: str = "ventas_correlaciones"
    grupos: str = "ventas_por_region"
    modelo: str = "ventas_modelo_historico"
    limpieza: str = "ventas_limpieza_historico"

    def as_mapping(self) -> dict[str, str]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class VentasPipelineOptions:
    max_retries: int = 1
    retry_backoff_s: float = 1.0
    segment_depth: int = 2  # 2^2 = 4 segmentos de ingreso
    tables: VentasTables = field(default_factory=VentasTables)


def build_ventas_pipeline(
    extractor: DataExtractor,
    loader: DataLoader | None,
    history_loader: DataLoader | None,
    options: VentasPipelineOptions | None = None,
) -> PipelineOrchestrator:
    opts = options or VentasPipelineOptions()

    transformer = FeatureTransformer([
        RevenueFeatures(),
        DateFeatures("fecha"),
        LogTransform(["gasto_publicidad", "ingreso_neto"]),
        ZScoreScaler(["precio_unitario", "gasto_publicidad"]),
        MedianSegmenter("ingreso_neto", depth=opts.segment_depth),
    ])

    orchestrator = PipelineOrchestrator(max_retries=opts.max_retries, retry_backoff_s=opts.retry_backoff_s)
    orchestrator.register(ExtractStep(extractor))
    orchestrator.register(CleanStep(DataCleaner(VENTAS_CLEANING)))
    orchestrator.register(TransformStep(transformer))
    orchestrator.register(DescriptiveStep(DescriptiveAnalyzer(
        numeric_columns=(*NUMERIC, "ingreso_bruto", "ingreso_neto"),
        group_by="ubicacion_region",
        value_column="ingreso_neto",
    )))
    # Modelo de demanda: unidades vendidas en función de publicidad, precio y descuento
    orchestrator.register(RegressionStep(LinearRegressionModel(
        target="cantidad",
        features=("gasto_publicidad", "precio_unitario", "descuento"),
    )))
    if loader is not None and history_loader is not None:
        orchestrator.register(LoadStep(loader, history_loader, opts.tables.as_mapping()))
    return orchestrator
