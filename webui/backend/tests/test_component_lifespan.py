from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

import app.main as main_module
import app.components as components_module
import app.routers.analysis as analysis_module


class Provider:
    model_modules: tuple[str, ...] = ()

    def __init__(self, name: str, events: list[str], *, fail_start=False, fail_stop=False):
        self.name = name
        self.events = events
        self.fail_start = fail_start
        self.fail_stop = fail_stop

    async def startup(self, app: FastAPI) -> None:
        del app
        self.events.append(f"start:{self.name}")
        if self.fail_start:
            raise RuntimeError(f"start failed: {self.name}")

    async def shutdown(self, app: FastAPI) -> None:
        del app
        self.events.append(f"stop:{self.name}")
        if self.fail_stop:
            raise RuntimeError(f"stop failed: {self.name}")


def _disable_database_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module, "init_db", lambda **_kwargs: None)
    monkeypatch.setattr(main_module, "get_engine", lambda: object())
    monkeypatch.setattr(main_module, "selected_protocol", lambda: SimpleNamespace())
    monkeypatch.setattr(main_module, "ensure_study_binding", lambda *_args: None)
    monkeypatch.setattr(
        analysis_module, "reconcile_interrupted_bayes_jobs", lambda _engine: 0
    )
    monkeypatch.setattr(analysis_module, "shutdown_bayes_jobs", lambda _engine: 0)
    monkeypatch.setattr(
        analysis_module, "acquire_backend_instance_lease", lambda _engine: None
    )
    monkeypatch.setattr(
        analysis_module, "release_backend_instance_lease", lambda _engine: True
    )


def test_partial_provider_startup_is_unwound(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    provider = Provider("partial", events, fail_start=True)
    monkeypatch.setattr(main_module, "_COMPONENT_PROVIDERS", (provider,))
    _disable_database_startup(monkeypatch)

    async def run() -> None:
        with pytest.raises(RuntimeError, match="start failed"):
            async with main_module.lifespan(FastAPI()):
                pytest.fail("startup failure must prevent application service")

    asyncio.run(run())
    assert events == ["start:partial", "stop:partial"]


def test_one_shutdown_failure_does_not_skip_other_provider_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    first = Provider("first", events)
    second = Provider("second", events, fail_stop=True)
    monkeypatch.setattr(main_module, "_COMPONENT_PROVIDERS", (first, second))
    _disable_database_startup(monkeypatch)

    async def run() -> None:
        with pytest.raises(RuntimeError, match="stop failed"):
            async with main_module.lifespan(FastAPI()):
                events.append("served")

    asyncio.run(run())
    assert events == ["start:first", "start:second", "served", "stop:second", "stop:first"]


def test_live_bayesian_compute_failure_retains_backend_database_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_database_startup(monkeypatch)
    monkeypatch.setattr(main_module, "_COMPONENT_PROVIDERS", ())
    released: list[object] = []
    monkeypatch.setattr(
        analysis_module,
        "shutdown_bayes_jobs",
        lambda _engine: (_ for _ in ()).throw(RuntimeError("workers still active")),
    )
    monkeypatch.setattr(
        analysis_module,
        "release_backend_instance_lease",
        lambda engine: released.append(engine),
    )

    async def run() -> None:
        with pytest.raises(RuntimeError, match="workers still active"):
            async with main_module.lifespan(FastAPI()):
                pass

    asyncio.run(run())
    assert released == []


def test_auto_component_discovery_ignores_only_an_absent_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(components_module, "_ACTIVE_REGISTRY", components_module._ACTIVE_REGISTRY)
    def absent(entrypoint: str):
        module_name = entrypoint.split(":", 1)[0]
        raise ModuleNotFoundError(f"No module named {module_name!r}", name=module_name)

    monkeypatch.setattr(components_module, "_load_entrypoint", absent)
    registry, providers = components_module.configure_components("auto")

    assert providers == ()
    assert all(manifest.distribution == "core" for manifest in registry.manifests())


def test_auto_component_discovery_surfaces_broken_transitive_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(_entrypoint: str):
        raise ModuleNotFoundError("No module named 'missing_driver'", name="missing_driver")

    monkeypatch.setattr(components_module, "_load_entrypoint", broken)
    with pytest.raises(ModuleNotFoundError, match="missing_driver"):
        components_module.configure_components("auto")
