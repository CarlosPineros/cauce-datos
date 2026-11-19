"""
Contratos (puertos) del dominio.

Principios aplicados:
- ISP: interfaces pequeñas y específicas (extraer, cargar, ejecutar un paso).
- DIP: las capas superiores dependen de estas abstracciones, no de S3/PostgreSQL.
- LSP: cualquier implementación es intercambiable sin cambiar a quien la usa.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

    from .models import PipelineContext


class DataExtractor(ABC):
    """Lee datos desde una fuente y los devuelve como DataFrame."""

    @abstractmethod
    def extract(self) -> pd.DataFrame: ...


class DataLoader(ABC):
    """Persiste un DataFrame en un destino con un nombre lógico (tabla, archivo...)."""

    @abstractmethod
    def load(self, df: pd.DataFrame, target: str) -> int:
        """Devuelve el número de filas escritas."""


class PipelineStep(ABC):
    """
    Unidad de trabajo del orquestador. Lee y escribe artefactos en el contexto.
    Nuevos pasos se agregan creando subclases (OCP), sin tocar el orquestador.
    """

    #: Nombre único del paso.
    name: str = ""
    #: Nombres de los pasos que deben ejecutarse antes.
    depends_on: tuple[str, ...] = ()

    @abstractmethod
    def run(self, context: PipelineContext) -> None: ...
