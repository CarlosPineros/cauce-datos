"""
Línea de comandos del ETL.

    python -m etl                                   # S3 -> PostgreSQL (entorno de .env)
    python -m etl --entorno preproduccion
    python -m etl --fuente local --ruta ventas.csv  # lee data/ventas.csv
    python -m etl --sin-carga                       # solo extrae, limpia, transforma y modela
    python -m etl --entorno produccion --confirmar-produccion
"""
from __future__ import annotations

import argparse
import logging
import sys

from config import get_settings
from config.settings import BASE_DIR
from etl.domain import ETLError, PipelineContext
from etl.domain.validators import validate_identifier

ENTORNOS = ("produccion", "preproduccion", "prueba")
DATA_DIR = BASE_DIR / "data"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="etl", description="ETL de ventas: S3/archivo -> limpieza -> modelos -> PostgreSQL"
    )
    p.add_argument("--fuente", choices=("s3", "local"), default="s3")
    p.add_argument("--clave", default="datos/ventas.json", help="Clave del objeto en S3")
    p.add_argument("--ruta", default="ventas.json", help="Archivo dentro de ./data (fuente local)")
    p.add_argument("--entorno", choices=ENTORNOS, default=None, help="Base de datos destino (por defecto la de .env)")
    p.add_argument("--esquema", default="etl", help="Esquema PostgreSQL destino")
    p.add_argument("--sin-carga", action="store_true", help="No escribe en la base de datos")
    p.add_argument("--confirmar-produccion", action="store_true", help="Requerido para escribir en produccion")
    p.add_argument("--reintentos", type=int, default=1, choices=range(0, 6), metavar="0-5")
    p.add_argument("--log-level", default=None, choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    logging.basicConfig(
        level=args.log_level or settings.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    log = logging.getLogger("etl")

    # Importaciones de infraestructura aquí: solo la capa de presentación las conoce.
    from connections import PostgresClient, S3Client
    from etl.infrastructure import LocalFileExtractor, PostgresLoader, S3ObjectExtractor

    from .ventas_pipeline import VentasPipelineOptions, build_ventas_pipeline

    db_name = args.entorno or settings.postgres.db
    if db_name == "produccion" and not args.sin_carga and not args.confirmar_produccion:
        log.error("Para escribir en 'produccion' agrega --confirmar-produccion")
        return 2

    db: PostgresClient | None = None
    try:
        schema = validate_identifier(args.esquema)
        extractor = (
            S3ObjectExtractor(S3Client(), args.clave)
            if args.fuente == "s3"
            else LocalFileExtractor(DATA_DIR, args.ruta)
        )
        loader = history = None
        if not args.sin_carga:
            db = PostgresClient(settings.postgres.model_copy(update={"db": db_name}))
            loader = PostgresLoader(db, schema=schema, mode="replace")
            history = PostgresLoader(db, schema=schema, mode="append")

        pipeline = build_ventas_pipeline(extractor, loader, history, VentasPipelineOptions(max_retries=args.reintentos))
        log.info("Destino: %s", "sin carga" if args.sin_carga else f"{db_name}.{schema}")
        context = PipelineContext(params={"entorno": db_name})
        report = pipeline.run(context)
    except ETLError as exc:
        log.error("Configuración inválida: %s", exc)
        return 2
    finally:
        if db is not None:
            db.close()

    print(report.summary())
    if context.has("regression_result"):
        r = context.get("regression_result")
        print(f"\nModelo: {r.equation()}")
        print(f"  R²={r.r2:.4f}  R²aj={r.adj_r2:.4f}  RMSE={r.rmse:.3f}  MAE={r.mae:.3f}  n={r.n_obs}")
    return 0 if report.success else 1


if __name__ == "__main__":
    sys.exit(main())
