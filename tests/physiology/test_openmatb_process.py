from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest

from matb_integration.physiology.openmatb_process import (
    OpenMATBLauncher,
    OpenMATBProcessError,
)


def test_launcher_builds_shell_free_synchronized_command(tmp_path: Path) -> None:
    scenario_root = tmp_path / "scenarios"
    scenario = scenario_root / "military_aviation" / "low_workload.txt"
    scenario.parent.mkdir(parents=True)
    scenario.write_text("0:00:00;track;start\n", encoding="utf-8")
    openmatb_root = tmp_path / "openmatb"
    openmatb_root.mkdir()
    (openmatb_root / "main.py").write_text("", encoding="utf-8")
    (openmatb_root / "launch_contract.py").write_text("", encoding="utf-8")
    (openmatb_root / "config.ini").write_text("[Openmatb]\n", encoding="utf-8")
    (openmatb_root / "VERSION").write_text("test\n", encoding="utf-8")
    (openmatb_root / "requirements.txt").write_text("pyglet\n", encoding="utf-8")
    launcher = OpenMATBLauncher(
        openmatb_root=openmatb_root,
        scenario_root=scenario_root,
        python_executable="python-for-openmatb",
    )

    command = launcher.build_command(
        scenario_name="military_aviation/low_workload.txt",
        session_id="de4ad40d-7cbb-4b2a-a4c6-9f839a086c4e",
        output_dir=tmp_path / "capture",
    )

    assert command == (
        "python-for-openmatb",
        str((openmatb_root / "main.py").resolve()),
        "--scenario",
        str(scenario.resolve()),
        "--session-id",
        "de4ad40d-7cbb-4b2a-a4c6-9f839a086c4e",
        "--output-dir",
        str((tmp_path / "capture").resolve()),
    )
    assert launcher.scenario_sha256("military_aviation/low_workload.txt") == hashlib.sha256(
        scenario.read_bytes()
    ).hexdigest()
    assert len(launcher.application_sha256()) == 64
    with pytest.raises(OpenMATBProcessError, match="scenario_path_invalid"):
        launcher.build_command(
            scenario_name="../outside.txt",
            session_id="de4ad40d-7cbb-4b2a-a4c6-9f839a086c4e",
            output_dir=tmp_path / "capture",
        )


def test_application_digest_tracks_runtime_inputs_but_excludes_tests_and_caches(
    tmp_path: Path,
) -> None:
    openmatb_root = tmp_path / "openmatb"
    for directory in (
        "core",
        "plugins",
        "includes/questionnaires",
        "locales/en_EN/LC_MESSAGES",
        "tests",
        "core/__pycache__",
    ):
        (openmatb_root / directory).mkdir(parents=True, exist_ok=True)
    for relative, content in {
        "main.py": "from core import scheduler\n",
        "launch_contract.py": "CONTRACT = 1\n",
        "config.ini": "[Openmatb]\nlanguage=en_EN\n",
        "VERSION": "1.4.5\n",
        "requirements.txt": "pyglet==2.0\n",
        "core/scheduler.py": "TASK_SECONDS = 900\n",
        "plugins/genericscales.py": "TITLE = 'NASA-TLX'\n",
        "includes/questionnaires/NASA-TLX.txt": "Mental demand\n",
        "locales/en_EN/LC_MESSAGES/openmatb.mo": "compiled locale\n",
        "tests/test_scheduler.py": "assert True\n",
        "core/__pycache__/scheduler.pyc": "cache\n",
    }.items():
        (openmatb_root / relative).write_text(content, encoding="utf-8")
    scenario_root = tmp_path / "scenarios"
    scenario_root.mkdir()
    launcher = OpenMATBLauncher(
        openmatb_root=openmatb_root,
        scenario_root=scenario_root,
    )

    original = launcher.application_sha256()
    (openmatb_root / "tests/test_scheduler.py").write_text(
        "raise AssertionError\n",
        encoding="utf-8",
    )
    (openmatb_root / "core/__pycache__/scheduler.pyc").write_text(
        "different cache\n",
        encoding="utf-8",
    )
    assert launcher.application_sha256() == original

    (openmatb_root / "config.ini").write_text(
        "[Openmatb]\nlanguage=fr_FR\n",
        encoding="utf-8",
    )
    after_config = launcher.application_sha256()
    assert after_config != original

    (openmatb_root / "includes/questionnaires/NASA-TLX.txt").write_text(
        "Mental demand\nEffort\n",
        encoding="utf-8",
    )
    assert launcher.application_sha256() != after_config


def test_launcher_returns_the_exact_csv_and_event_sidecar(tmp_path: Path) -> None:
    scenario_root = tmp_path / "scenarios"
    scenario = scenario_root / "military_aviation" / "low_workload.txt"
    scenario.parent.mkdir(parents=True)
    scenario.write_text("0:00:00;track;start\n", encoding="utf-8")
    openmatb_root = tmp_path / "openmatb"
    openmatb_root.mkdir()
    (openmatb_root / "main.py").write_text("", encoding="utf-8")

    class FakeProcess:
        returncode = 0

        async def wait(self) -> int:
            return 0

        def terminate(self) -> None:
            self.returncode = -15

        def kill(self) -> None:
            self.returncode = -9

    process_kwargs = {}

    async def process_factory(*arguments, **kwargs):
        process_kwargs.update(kwargs)
        output = Path(arguments[arguments.index("--output-dir") + 1])
        output.mkdir(parents=True, exist_ok=True)
        (output / "openmatb-session.csv").write_text(
            "logtime,scenario_time,type,module,address,value\n",
            encoding="utf-8",
        )
        (output / "openmatb-events.jsonl").write_text(
            '{"event":"scenario_finished"}\n',
            encoding="utf-8",
        )
        return FakeProcess()

    launcher = OpenMATBLauncher(
        openmatb_root=openmatb_root,
        scenario_root=scenario_root,
        process_factory=process_factory,
    )

    result = asyncio.run(
        launcher.run(
            scenario_name="military_aviation/low_workload.txt",
            session_id="de4ad40d-7cbb-4b2a-a4c6-9f839a086c4e",
            output_dir=tmp_path / "capture",
        )
    )

    assert result.exit_code == 0
    assert result.source_csv.name == "openmatb-session.csv"
    assert result.synchronized_events.name == "openmatb-events.jsonl"
    assert int(process_kwargs["env"]["OPENMATB_PARENT_PID"]) > 0


def test_cancelling_run_terminates_the_spawned_child(tmp_path: Path) -> None:
    scenario_root = tmp_path / "scenarios"
    scenario = scenario_root / "military_aviation" / "low_workload.txt"
    scenario.parent.mkdir(parents=True)
    scenario.write_text("0:00:00;track;start\n", encoding="utf-8")
    openmatb_root = tmp_path / "openmatb"
    openmatb_root.mkdir()
    (openmatb_root / "main.py").write_text("", encoding="utf-8")
    spawned = asyncio.Event()

    class BlockingProcess:
        returncode = None
        terminate_count = 0
        kill_count = 0

        def __init__(self) -> None:
            self.finished = asyncio.Event()

        async def wait(self) -> int:
            await self.finished.wait()
            return int(self.returncode)

        def terminate(self) -> None:
            self.terminate_count += 1
            self.returncode = -15
            self.finished.set()

        def kill(self) -> None:
            self.kill_count += 1
            self.returncode = -9
            self.finished.set()

    process = BlockingProcess()

    async def process_factory(*arguments, **_kwargs):
        output = Path(arguments[arguments.index("--output-dir") + 1])
        output.mkdir(parents=True, exist_ok=True)
        (output / "openmatb-session.csv").write_text(
            "logtime,scenario_time,type,module,address,value\n",
            encoding="utf-8",
        )
        (output / "openmatb-events.jsonl").write_text("", encoding="utf-8")
        spawned.set()
        return process

    launcher = OpenMATBLauncher(
        openmatb_root=openmatb_root,
        scenario_root=scenario_root,
        process_factory=process_factory,
    )

    async def scenario_run() -> None:
        task = asyncio.create_task(
            launcher.run(
                scenario_name="military_aviation/low_workload.txt",
                session_id="de4ad40d-7cbb-4b2a-a4c6-9f839a086c4e",
                output_dir=tmp_path / "cancel-capture",
            )
        )
        await spawned.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario_run())

    assert process.terminate_count == 1
    assert process.kill_count == 0
    assert launcher._process is None


def test_abort_waits_for_in_flight_process_startup_then_terminates(tmp_path: Path) -> None:
    scenario_root = tmp_path / "scenarios"
    scenario = scenario_root / "military_aviation" / "low_workload.txt"
    scenario.parent.mkdir(parents=True)
    scenario.write_text("0:00:00;track;start\n", encoding="utf-8")
    openmatb_root = tmp_path / "openmatb"
    openmatb_root.mkdir()
    (openmatb_root / "main.py").write_text("", encoding="utf-8")
    factory_entered = asyncio.Event()
    allow_spawn = asyncio.Event()

    class BlockingProcess:
        returncode = None
        terminate_count = 0

        def __init__(self) -> None:
            self.finished = asyncio.Event()

        async def wait(self) -> int:
            await self.finished.wait()
            return int(self.returncode)

        def terminate(self) -> None:
            self.terminate_count += 1
            self.returncode = -15
            self.finished.set()

        def kill(self) -> None:
            self.returncode = -9
            self.finished.set()

    process = BlockingProcess()

    async def process_factory(*arguments, **_kwargs):
        factory_entered.set()
        await allow_spawn.wait()
        output = Path(arguments[arguments.index("--output-dir") + 1])
        output.mkdir(parents=True, exist_ok=True)
        (output / "openmatb-session.csv").write_text(
            "logtime,scenario_time,type,module,address,value\n",
            encoding="utf-8",
        )
        (output / "openmatb-events.jsonl").write_text("", encoding="utf-8")
        return process

    launcher = OpenMATBLauncher(
        openmatb_root=openmatb_root,
        scenario_root=scenario_root,
        process_factory=process_factory,
    )

    async def scenario_run() -> None:
        run_task = asyncio.create_task(
            launcher.run(
                scenario_name="military_aviation/low_workload.txt",
                session_id="de4ad40d-7cbb-4b2a-a4c6-9f839a086c4e",
                output_dir=tmp_path / "startup-capture",
            )
        )
        await factory_entered.wait()
        abort_task = asyncio.create_task(launcher.abort())
        await asyncio.sleep(0)
        assert not abort_task.done()
        allow_spawn.set()
        await abort_task
        result = await run_task
        assert result.exit_code == -15

    asyncio.run(scenario_run())

    assert process.terminate_count == 1
