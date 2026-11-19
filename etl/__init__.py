"""
ETL por capas:

    domain/          Entidades, contratos (interfaces) y errores. Sin dependencias externas.
    application/     Casos de uso: limpieza, transformación, modelos, pasos y orquestador.
    infrastructure/  Adaptadores concretos: S3, archivos locales, PostgreSQL.
    presentation/    Punto de entrada (CLI) y composición de dependencias.

Las dependencias siempre apuntan hacia adentro: presentation -> infrastructure
-> application -> domain.
"""

__version__ = "1.0.0"
