"""Entidades y objetos de valor del dominio."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class StepStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepResult:
    name: str
    status: StepStatus = StepStatus.PENDING
    duration_s: float = 0.0
    attempts: int = 0
    error: str | None = None


@dataclass
class PipelineReport:
    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    queue: list[str] = field(default_factory=list)
    steps: list[StepResult] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return bool(self.steps) and all(s.status == StepStatus.SUCCESS for s in self.steps)

    def summary(self) -> str:
        lines = [f"Pipeline {self.run_id}: {'OK' if self.success else 'FALLÓ'}"]
        for s in self.steps:
            extra = f" -> {s.error}" if s.error else ""
            lines.append(f"  [{s.status.value:^7}] {s.name} ({s.duration_s:.2f}s, intentos={s.attempts}){extra}")
        return "\n".join(lines)


class PipelineContext:
    """
    Almacén de artefactos compartido entre pasos (DataFrames, reportes, métricas).
    Evita que los pasos se conozcan entre sí: solo acuerdan nombres de artefactos.
    """

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        self.params: dict[str, Any] = dict(params or {})
        self._artifacts: dict[str, Any] = {}

    def put(self, key: str, value: Any) -> None:
        self._artifacts[key] = value

    def get(self, key: str) -> Any:
        if key not in self._artifacts:
            raise KeyError(f"Artefacto '{key}' no disponible en el contexto")
        return self._artifacts[key]

    def has(self, key: str) -> bool:
        return key in self._artifacts

    def keys(self) -> list[str]:
        return list(self._artifacts)


@dataclass(frozen=True)
class DescriptiveReport:
    """Resultado del modelo descriptivo."""

    row_count: int
    column_stats: dict[str, dict[str, float]]          # estadísticas por columna numérica
    correlations: dict[str, dict[str, float]]          # matriz de Pearson
    group_stats: list[dict[str, Any]]                  # agregados por categoría
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class RegressionResult:
    """Resultado del modelo matemático (regresión lineal por mínimos cuadrados)."""

    target: str
    features: tuple[str, ...]
    intercept: float
    coefficients: dict[str, float]
    r2: float
    adj_r2: float
    rmse: float
    mae: float
    n_obs: int

    def equation(self) -> str:
        terms = " ".join(f"{'+' if c >= 0 else '-'} {abs(c):.4f}·{f}" for f, c in self.coefficients.items())
        return f"{self.target} = {self.intercept:.4f} {terms}"
