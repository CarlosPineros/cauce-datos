"""Prueba de integración del pipeline completo con extractor y loader en memoria."""
from etl.domain import PipelineContext
from etl.infrastructure.parsers import records_to_frame
from etl.presentation import VentasPipelineOptions, build_ventas_pipeline

from .conftest import InMemoryExtractor


def test_pipeline_completo(ventas_records, in_memory_loader):
    history = type(in_memory_loader)()
    pipeline = build_ventas_pipeline(
        InMemoryExtractor(records_to_frame(ventas_records)),
        in_memory_loader,
        history,
        VentasPipelineOptions(max_retries=0),
    )
    ctx = PipelineContext()
    report = pipeline.run(ctx)

    assert report.success, report.summary()
    assert report.queue == ["extraer", "limpiar", "transformar", "describir", "modelar", "cargar"]
    assert set(in_memory_loader.tables) == {
        "ventas_datos", "ventas_estadisticas", "ventas_correlaciones", "ventas_por_region",
    }
    assert set(history.tables) == {"ventas_modelo_historico", "ventas_limpieza_historico"}

    datos = in_memory_loader.tables["ventas_datos"][0]
    for col in ("ingreso_neto", "segmento_ingreso_neto", "pred_cantidad", "residuo_cantidad", "z_precio_unitario"):
        assert col in datos.columns


def test_pipeline_sin_carga(ventas_records):
    pipeline = build_ventas_pipeline(InMemoryExtractor(records_to_frame(ventas_records)), None, None)
    report = pipeline.run()
    assert report.success
    assert "cargar" not in report.queue


def test_pipeline_falla_y_omite_resto():
    import pandas as pd

    pipeline = build_ventas_pipeline(InMemoryExtractor(pd.DataFrame({"x": [1]})), None, None,
                                     VentasPipelineOptions(max_retries=0))
    report = pipeline.run()
    assert not report.success
    assert [s.status.value for s in report.steps][:2] == ["success", "failed"]
    assert all(s.status.value == "skipped" for s in report.steps[2:])
