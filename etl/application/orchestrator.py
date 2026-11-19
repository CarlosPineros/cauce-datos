"""
Orquestador del pipeline.

1. Registra pasos (`PipelineStep`) con sus dependencias.
2. Construye la COLA de ejecución mediante un ordenamiento topológico RECURSIVO
   (DFS post-orden) que detecta ciclos y dependencias inexistentes.
3. Ejecuta la cola en orden, con reintentos y backoff exponencial por paso.
   Si un paso falla, los restantes se marcan como SKIPPED y se devuelve el reporte.

No conoce S3, PostgreSQL ni pandas: solo trabaja con abstracciones (DIP).
"""
from __future__ import annotations

import logging
import time
import uuid
from collections import deque
from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from etl.domain import (
    CyclicDependencyError,
    PipelineContext,
    PipelineReport,
    PipelineStep,
    PipelineStepError,
    StepResult,
    StepStatus,
)

logger = logging.getLogger(__name__)

MAX_STEPS = 200  # cota para la recursión del ordenamiento topológico


class PipelineOrchestrator:
    def __init__(
        self,
        steps: Iterable[PipelineStep] = (),
        max_retries: int = 0,
        retry_backoff_s: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries debe ser ≥ 0")
        self._steps: dict[str, PipelineStep] = {}
        self.max_retries = max_retries
        self.retry_backoff_s = retry_backoff_s
        self._sleep = sleep  # inyectable para pruebas
        for step in steps:
            self.register(step)

    # ------------------------------------------------------------ registro
    def register(self, step: PipelineStep) -> PipelineOrchestrator:
        if not step.name:
            raise ValueError(f"{type(step).__name__} no tiene nombre")
        if step.name in self._steps:
            raise ValueError(f"Paso duplicado: {step.name}")
        if len(self._steps) >= MAX_STEPS:
            raise ValueError(f"Máximo {MAX_STEPS} pasos por pipeline")
        self._steps[step.name] = step
        return self

    @property
    def step_names(self) -> list[str]:
        return list(self._steps)

    # --------------------------------------------------------------- cola
    def build_queue(self, targets: Iterable[str] | None = None) -> deque[str]:
        """
        Devuelve la cola de ejecución. Si se indican `targets`, solo incluye esos
        pasos y todas sus dependencias (transitivas).
        """
        targets = list(targets) if targets else list(self._steps)
        ordered: list[str] = []
        visited: set[str] = set()
        for name in targets:
            self._visit(name, visited, in_progress=(), ordered=ordered)
        return deque(ordered)

    def _visit(self, name: str, visited: set[str], in_progress: tuple[str, ...], ordered: list[str]) -> None:
        """
        DFS recursivo (post-orden):
          - caso base 1: el paso ya fue visitado -> nada que hacer
          - caso base 2: el paso está en la ruta actual -> hay un ciclo
          - caso recursivo: visitar primero cada dependencia y luego encolar el paso
        """
        if name in visited:
            return
        if name in in_progress:
            cycle = " -> ".join((*in_progress[in_progress.index(name):], name))
            raise CyclicDependencyError(f"Ciclo detectado: {cycle}")
        if name not in self._steps:
            origin = f" (requerido por '{in_progress[-1]}')" if in_progress else ""
            raise KeyError(f"Paso desconocido: '{name}'{origin}")

        for dep in self._steps[name].depends_on:
            self._visit(dep, visited, (*in_progress, name), ordered)

        visited.add(name)
        ordered.append(name)

    # ---------------------------------------------------------- ejecución
    def run(
        self,
        context: PipelineContext | None = None,
        targets: Iterable[str] | None = None,
        raise_on_error: bool = False,
    ) -> PipelineReport:
        context = context or PipelineContext()
        queue = self.build_queue(targets)
        report = PipelineReport(
            run_id=uuid.uuid4().hex[:12],
            started_at=datetime.now(UTC),
            queue=list(queue),
        )
        context.put("run_id", report.run_id)
        logger.info("Pipeline %s | cola: %s", report.run_id, " -> ".join(queue))

        failure: PipelineStepError | None = None
        while queue:
            name = queue.popleft()
            if failure is not None:
                report.steps.append(StepResult(name, StepStatus.SKIPPED))
                continue
            result = self._run_step(self._steps[name], context)
            report.steps.append(result)
            if result.status == StepStatus.FAILED:
                failure = PipelineStepError(name, RuntimeError(result.error or "error"))

        report.finished_at = datetime.now(UTC)
        logger.info("Pipeline %s finalizado: %s", report.run_id, "OK" if report.success else "FALLÓ")
        logger.debug("\n%s", report.summary())
        if failure is not None and raise_on_error:
            raise failure
        return report

    def _run_step(self, step: PipelineStep, context: PipelineContext) -> StepResult:
        result = StepResult(step.name)
        start = time.perf_counter()
        for attempt in range(1, self.max_retries + 2):
            result.attempts = attempt
            try:
                logger.info("▶ %s (intento %d)", step.name, attempt)
                step.run(context)
                result.status = StepStatus.SUCCESS
                result.error = None
                break
            except Exception as exc:  # noqa: BLE001 - se registra y decide reintento
                result.status = StepStatus.FAILED
                result.error = f"{type(exc).__name__}: {exc}"
                logger.warning("✖ %s falló en intento %d: %s", step.name, attempt, result.error)
                if attempt <= self.max_retries:
                    self._sleep(self.retry_backoff_s * 2 ** (attempt - 1))
        result.duration_s = time.perf_counter() - start
        return result
