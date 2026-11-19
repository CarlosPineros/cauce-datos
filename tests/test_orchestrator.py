import pytest

from etl.application import PipelineOrchestrator
from etl.domain import CyclicDependencyError, PipelineContext, PipelineStep, PipelineStepError, StepStatus


class Step(PipelineStep):
    def __init__(self, name, deps=(), fail_times=0, log=None):
        self.name = name
        self.depends_on = tuple(deps)
        self.fail_times = fail_times
        self.calls = 0
        self.log = log if log is not None else []

    def run(self, context):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError(f"fallo {self.calls}")
        self.log.append(self.name)


def orq(*steps, **kw):
    return PipelineOrchestrator(steps, sleep=lambda _: None, **kw)


def test_cola_respeta_dependencias():
    o = orq(Step("d", ["b", "c"]), Step("b", ["a"]), Step("c", ["a"]), Step("a"))
    queue = list(o.build_queue())
    assert queue.index("a") < queue.index("b") < queue.index("d")
    assert queue.index("a") < queue.index("c") < queue.index("d")
    assert len(queue) == 4


def test_targets_incluye_solo_dependencias_transitivas():
    o = orq(Step("a"), Step("b", ["a"]), Step("c", ["b"]), Step("x"))
    assert list(o.build_queue(["c"])) == ["a", "b", "c"]


def test_detecta_ciclos():
    o = orq(Step("a", ["c"]), Step("b", ["a"]), Step("c", ["b"]))
    with pytest.raises(CyclicDependencyError, match="Ciclo"):
        o.build_queue()


def test_dependencia_inexistente():
    with pytest.raises(KeyError, match="fantasma"):
        orq(Step("a", ["fantasma"])).build_queue()


def test_paso_duplicado():
    with pytest.raises(ValueError):
        orq(Step("a"), Step("a"))


def test_ejecuta_en_orden_y_reporta():
    log: list[str] = []
    report = orq(Step("b", ["a"], log=log), Step("a", log=log)).run()
    assert log == ["a", "b"]
    assert report.success
    assert report.queue == ["a", "b"]


def test_reintentos():
    flaky = Step("a", fail_times=2)
    report = orq(flaky, max_retries=2).run()
    assert report.success
    assert report.steps[0].attempts == 3


def test_fallo_omite_pasos_siguientes():
    report = orq(Step("a", fail_times=9), Step("b", ["a"])).run()
    assert not report.success
    assert [s.status for s in report.steps] == [StepStatus.FAILED, StepStatus.SKIPPED]


def test_raise_on_error():
    with pytest.raises(PipelineStepError):
        orq(Step("a", fail_times=9)).run(raise_on_error=True)


def test_contexto_compartido():
    class Productor(PipelineStep):
        name = "p"

        def run(self, context):
            context.put("dato", 42)

    class Consumidor(PipelineStep):
        name = "c"
        depends_on = ("p",)

        def run(self, context):
            context.put("doble", context.get("dato") * 2)

    ctx = PipelineContext()
    orq(Consumidor(), Productor()).run(ctx)
    assert ctx.get("doble") == 84
