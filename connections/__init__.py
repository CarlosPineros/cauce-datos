"""
Conexiones reutilizables. Las importaciones son perezosas para que un módulo
no exija instalar las dependencias de los demás (p. ej. usar S3 sin psycopg).
"""
from typing import TYPE_CHECKING

__all__ = ["AzureCLI", "AzureCLIError", "PostgresClient", "S3Client"]

if TYPE_CHECKING:
    from .azure_cli import AzureCLI, AzureCLIError
    from .postgres import PostgresClient
    from .s3 import S3Client


def __getattr__(name: str):
    if name == "PostgresClient":
        from .postgres import PostgresClient
        return PostgresClient
    if name in ("AzureCLI", "AzureCLIError"):
        from . import azure_cli
        return getattr(azure_cli, name)
    if name == "S3Client":
        from .s3 import S3Client
        return S3Client
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
