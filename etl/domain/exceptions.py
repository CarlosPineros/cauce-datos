"""Jerarquía de errores del ETL. Los mensajes nunca incluyen credenciales."""


class ETLError(Exception):
    """Error base del ETL."""


class ExtractionError(ETLError):
    """Fallo al leer datos de una fuente."""


class LoadError(ETLError):
    """Fallo al escribir datos en el destino."""


class DataValidationError(ETLError):
    """Los datos no cumplen el esquema o reglas esperadas."""


class UnsafeInputError(ETLError):
    """Entrada rechazada por motivos de seguridad (identificadores, rutas, tamaños)."""


class CyclicDependencyError(ETLError):
    """El grafo de pasos del pipeline contiene un ciclo."""


class PipelineStepError(ETLError):
    """Un paso del pipeline falló."""

    def __init__(self, step_name: str, cause: Exception) -> None:
        self.step_name = step_name
        self.cause = cause
        super().__init__(f"El paso '{step_name}' falló: {type(cause).__name__}: {cause}")
