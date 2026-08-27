"""Shell-free native OpenMATB process orchestration for synchronized sessions."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import sys
from typing import Any
from uuid import UUID

from .durability import make_private_directory


class OpenMATBProcessError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class OpenMATBProcessResult:
    exit_code: int
    source_csv: Path
    synchronized_events: Path
    stdout_log: Path
    stderr_log: Path
    started_at: datetime
    finished_at: datetime


ProcessFactory = Callable[..., Awaitable[Any]]

_RUNTIME_MANIFEST_VERSION = b"openmatb-runtime-manifest-v1\0"
_RUNTIME_REQUIRED_FILES = (
    "main.py",
    "launch_contract.py",
    "config.ini",
    "VERSION",
    "requirements.txt",
)
_RUNTIME_PYTHON_TREES = ("core", "plugins")
_RUNTIME_ASSET_TREES = (
    "includes/questionnaires",
    "includes/instructions",
    "includes/sounds",
    "includes/img",
)


class OpenMATBLauncher:
    def __init__(
        self,
        *,
        openmatb_root: Path,
        scenario_root: Path,
        python_executable: str | Path = sys.executable,
        process_factory: ProcessFactory = asyncio.create_subprocess_exec,
    ) -> None:
        self.openmatb_root = Path(openmatb_root).resolve()
        self.scenario_root = Path(scenario_root).resolve()
        self.python_executable = str(python_executable)
        self._process_factory = process_factory
        self._process: Any | None = None
        self._transition_lock = asyncio.Lock()
        self._termination_lock = asyncio.Lock()

    def available_scenarios(self) -> tuple[str, ...]:
        if not self.scenario_root.is_dir():
            return ()
        return tuple(
            sorted(
                path.relative_to(self.scenario_root).as_posix()
                for path in self.scenario_root.glob("military_aviation/*.txt")
                if path.is_file()
            )
        )

    def resolve_scenario(self, scenario_name: str) -> Path:
        relative = Path(scenario_name)
        if (
            not scenario_name
            or relative.is_absolute()
            or ".." in relative.parts
            or relative.suffix.casefold() != ".txt"
        ):
            raise OpenMATBProcessError("scenario_path_invalid")
        scenario = (self.scenario_root / relative).resolve()
        if self.scenario_root not in scenario.parents or not scenario.is_file():
            raise OpenMATBProcessError("scenario_path_invalid")
        if scenario_name not in self.available_scenarios():
            raise OpenMATBProcessError("scenario_not_allowlisted")
        return scenario

    def scenario_sha256(self, scenario_name: str) -> str:
        """Hash the exact allowlisted scenario bytes used for this attempt."""

        scenario = self.resolve_scenario(scenario_name)
        try:
            return hashlib.sha256(scenario.read_bytes()).hexdigest()
        except OSError as exc:
            raise OpenMATBProcessError("scenario_read_failed") from exc

    def application_sha256(self) -> str:
        """Hash the explicit code, configuration, dependency, and asset manifest."""

        required = tuple(
            self.openmatb_root / relative
            for relative in _RUNTIME_REQUIRED_FILES
        )
        if any(not path.is_file() for path in required):
            raise OpenMATBProcessError("openmatb_source_missing")
        manifest_files: set[Path] = set(required)
        for relative in _RUNTIME_PYTHON_TREES:
            root = self.openmatb_root / relative
            if root.is_dir():
                manifest_files.update(
                    path
                    for path in root.rglob("*.py")
                    if path.is_file() and "__pycache__" not in path.parts
                )
        for relative in _RUNTIME_ASSET_TREES:
            root = self.openmatb_root / relative
            if root.is_dir():
                manifest_files.update(path for path in root.rglob("*") if path.is_file())
        locale_root = self.openmatb_root / "locales"
        if locale_root.is_dir():
            manifest_files.update(
                path for path in locale_root.rglob("*.mo") if path.is_file()
            )

        source_files = sorted(
            manifest_files,
            key=lambda path: path.relative_to(self.openmatb_root).as_posix(),
        )
        digest = hashlib.sha256()
        digest.update(_RUNTIME_MANIFEST_VERSION)
        try:
            for path in source_files:
                relative = path.relative_to(self.openmatb_root).as_posix().encode("utf-8")
                digest.update(len(relative).to_bytes(4, "big"))
                digest.update(relative)
                payload = path.read_bytes()
                digest.update(len(payload).to_bytes(8, "big"))
                digest.update(payload)
        except OSError as exc:
            raise OpenMATBProcessError("openmatb_source_read_failed") from exc
        return digest.hexdigest()

    def build_command(
        self,
        *,
        scenario_name: str,
        session_id: str,
        output_dir: Path,
    ) -> tuple[str, ...]:
        scenario = self.resolve_scenario(scenario_name)
        try:
            parsed_session_id = UUID(session_id)
        except (TypeError, ValueError, AttributeError) as exc:
            raise OpenMATBProcessError("session_id_invalid") from exc
        if str(parsed_session_id) != session_id.casefold():
            raise OpenMATBProcessError("session_id_invalid")
        entrypoint = (self.openmatb_root / "main.py").resolve()
        if not entrypoint.is_file():
            raise OpenMATBProcessError("openmatb_entrypoint_missing")
        return (
            self.python_executable,
            str(entrypoint),
            "--scenario",
            str(scenario),
            "--session-id",
            str(parsed_session_id),
            "--output-dir",
            str(Path(output_dir).resolve()),
        )

    async def run(
        self,
        *,
        scenario_name: str,
        session_id: str,
        output_dir: Path,
    ) -> OpenMATBProcessResult:
        capture_dir = Path(output_dir).resolve()
        command = self.build_command(
            scenario_name=scenario_name,
            session_id=session_id,
            output_dir=capture_dir,
        )
        make_private_directory(capture_dir)
        stdout_path = capture_dir / "openmatb.stdout.log"
        stderr_path = capture_dir / "openmatb.stderr.log"
        if stdout_path.exists() or stderr_path.exists():
            raise OpenMATBProcessError("openmatb_capture_immutable")
        started_at = datetime.now(timezone.utc)
        child_environment = os.environ.copy()
        child_environment["OPENMATB_PARENT_PID"] = str(os.getpid())
        process_kwargs: dict[str, Any] = {
            "cwd": str(self.openmatb_root),
            "env": child_environment,
        }
        if sys.platform == "win32":
            process_kwargs["creationflags"] = 0x00000200  # CREATE_NEW_PROCESS_GROUP
        else:
            process_kwargs["start_new_session"] = True
        process: Any | None = None
        try:
            with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
                process_kwargs["stdout"] = stdout
                process_kwargs["stderr"] = stderr
                async with self._transition_lock:
                    if self._process is not None and self._process.returncode is None:
                        raise OpenMATBProcessError("openmatb_process_active")
                    creation = asyncio.ensure_future(
                        self._process_factory(*command, **process_kwargs)
                    )
                    try:
                        process = await asyncio.shield(creation)
                    except asyncio.CancelledError:
                        # Subprocess creation can cross the OS spawn boundary
                        # before its awaitable reports cancellation.  Shield it,
                        # retrieve the handle, and reap that child before the
                        # cancelled launch coroutine is allowed to exit.
                        process = await creation
                        self._process = process
                        await self._terminate_process(process, timeout_seconds=5.0)
                        self._process = None
                        raise
                    self._process = process
                try:
                    exit_code = int(await process.wait())
                except asyncio.CancelledError:
                    await self._terminate_process(process, timeout_seconds=5.0)
                    raise
        finally:
            async with self._transition_lock:
                if process is not None and self._process is process:
                    self._process = None
        finished_at = datetime.now(timezone.utc)
        source_csv = capture_dir / "openmatb-session.csv"
        events = capture_dir / "openmatb-events.jsonl"
        if not source_csv.is_file():
            raise OpenMATBProcessError("openmatb_csv_missing")
        if not events.is_file():
            raise OpenMATBProcessError("openmatb_events_missing")
        return OpenMATBProcessResult(
            exit_code=exit_code,
            source_csv=source_csv,
            synchronized_events=events,
            stdout_log=stdout_path,
            stderr_log=stderr_path,
            started_at=started_at,
            finished_at=finished_at,
        )

    async def abort(self, *, timeout_seconds: float = 5.0) -> None:
        # Serialize with process creation so an abort cannot return in the
        # narrow interval after the OS spawned a child but before its handle was
        # published to this launcher.
        async with self._transition_lock:
            process = self._process
        if process is None or process.returncode is not None:
            return
        await self._terminate_process(process, timeout_seconds=timeout_seconds)

    async def _terminate_process(self, process: Any, *, timeout_seconds: float) -> None:
        async with self._termination_lock:
            if process.returncode is not None:
                return
            try:
                process.terminate()
            except ProcessLookupError:
                return
            try:
                await asyncio.wait_for(
                    asyncio.shield(process.wait()),
                    timeout=max(0.1, timeout_seconds),
                )
            except TimeoutError:
                if process.returncode is None:
                    with suppress(ProcessLookupError):
                        process.kill()
                await process.wait()


__all__ = [
    "OpenMATBLauncher",
    "OpenMATBProcessError",
    "OpenMATBProcessResult",
]
