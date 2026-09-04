"""Supervise native OpenMATB processes from the local research console."""

from __future__ import annotations

import asyncio
import ctypes
import hashlib
import json
import os
import platform
import secrets
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from aircraft_monitor.research.protocol import WorkloadLevel
from app.ingestion import IngestionError, ingest_csv
from app.models import Participant, Visit
from app.openmatb_models import OpenMatbInstructionProtocol, OpenMatbPresetSet, OpenMatbSuiteSession
from app.openmatb_schemas import (
    CloneInstructionRequest,
    ClonePresetRequest,
    CreateOpenMatbSession,
    InstructionProtocolView,
    OpenMatbReadiness,
    OpenMatbSessionView,
    PreparedOpenMatbSession,
    PresetSetView,
    ProfileSettings,
    UpdateInstructionRequest,
    UpdatePresetRequest,
    WorkloadScaleRequest,
)
from app.study_protocol import selected_protocol
from matb_integration.scenario_builder import (
    BEDFORD_QUESTIONNAIRE_ES,
    ISA_QUESTIONNAIRE_ES,
    NASATLX_QUESTIONNAIRE_ES,
    _write_scenario_with_manifest,
    block_order_for_participant,
    build_block_scenario,
    detect_generator_source_provenance,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


DEFAULT_PROFILES: dict[str, dict[str, float | int]] = {
    "PRACTICE": {"duration_seconds": 180, "difficulty": 0.15, "track_target_proportion": 0.90, "resman_loss_per_min": 100, "isa_probe_interval_sec": 90},
    "LOW": {"duration_seconds": 900, "difficulty": 0.20, "track_target_proportion": 0.80, "resman_loss_per_min": 200, "isa_probe_interval_sec": 90},
    "MEDIUM": {"duration_seconds": 900, "difficulty": 0.50, "track_target_proportion": 0.50, "resman_loss_per_min": 600, "isa_probe_interval_sec": 60},
    "HIGH": {"duration_seconds": 900, "difficulty": 0.80, "track_target_proportion": 0.20, "resman_loss_per_min": 1000, "isa_probe_interval_sec": 45},
}

DEFAULT_INSTRUCTIONS = {
    "title": "Instrucciones para la sesión MATB-FAC",
    "steps": [
        "Confirme con el investigador su código de participante, la visita y el día programado.",
        "Ajuste la silla y verifique la segunda pantalla, el audio, el mouse y el teclado o joystick.",
        "Lea las instrucciones de TRACK, COMM, SYSMON y RESMAN antes de iniciar la práctica.",
        "Complete la práctica y avise al investigador si algún control o sonido no funciona.",
        "Durante cada bloque responda solamente con los controles indicados y mantenga la atención en las cuatro tareas.",
        "Al finalizar cada bloque complete NASA-TLX y Bedford en esta pantalla.",
        "Espere la indicación del investigador antes de comenzar el siguiente bloque.",
    ],
    "task_instructions": {
        "TRACK": "Mantenga el cursor dentro del objetivo usando el joystick o mouse configurado.",
        "COMM": "Escuche los mensajes y responda únicamente cuando correspondan a su indicativo.",
        "SYSMON": "Detecte y corrija las luces o escalas que cambien al estado de falla.",
        "RESMAN": "Controle las bombas para mantener los niveles de combustible cerca de sus objetivos.",
    },
    "visit_instructions": {
        "DEFAULT": "Esta es una instancia programada del protocolo. Confirme el día y la visita con el investigador antes de iniciar.",
        "T0": "Día 0 · sesión inicial. Realice primero la práctica; luego complete los tres bloques y sus escalas después de cada bloque.",
        "DM8": "Día 8 · primera sesión de seguimiento. Repita la práctica y los tres bloques siguiendo las mismas instrucciones de la sesión inicial.",
        "DM15": "Día 15 · segunda sesión de seguimiento. Repita la práctica y los tres bloques; complete cada escala según su experiencia en el bloque actual.",
    },
}


class OpenMatbRuntimeError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _WindowsJob:
    """Own a Windows Job Object that terminates the complete native process tree."""

    def __init__(self, process_id: int) -> None:
        if os.name != "nt":
            raise OSError("Windows Job Objects are only available on Windows")

        from ctypes import wintypes

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
            )]

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimits), ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.OpenProcess.restype = wintypes.HANDLE
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            limits = ExtendedLimits()
            limits.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise ctypes.WinError(ctypes.get_last_error())
            process = kernel32.OpenProcess(0x0001 | 0x0100, False, process_id)
            if not process:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                if not kernel32.AssignProcessToJobObject(job, process):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                kernel32.CloseHandle(process)
        except BaseException:
            kernel32.CloseHandle(job)
            raise
        self._kernel32 = kernel32
        self._handle = job

    def close(self) -> None:
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


@dataclass
class _ProcessHandle:
    session_id: str
    block: str
    process: asyncio.subprocess.Process
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    exited: asyncio.Event = field(default_factory=asyncio.Event)
    session_csv: Path | None = None
    stderr: list[str] = field(default_factory=list)
    monitor: asyncio.Task[None] | None = None
    windows_job: _WindowsJob | None = None


class OpenMatbManager:
    def __init__(self, *, engine, repo_root: Path, artifact_root: Path, python_executable: Path | None = None) -> None:
        self.engine = engine
        self.repo_root = repo_root.resolve()
        self.openmatb_root = self.repo_root / "openmatb"
        self.artifact_root = artifact_root.resolve()
        self.python_executable = (python_executable or Path(sys.executable)).resolve()
        self._lock = asyncio.Lock()
        self._handles: dict[str, _ProcessHandle] = {}
        self._seed_defaults()
        self._mark_interrupted()

    def _seed_defaults(self) -> None:
        with Session(self.engine) as db:
            if db.exec(select(OpenMatbPresetSet).where(OpenMatbPresetSet.preset_id == "matb-fac-standard", OpenMatbPresetSet.version == "1.0.0")).first() is None:
                db.add(OpenMatbPresetSet(
                    preset_id="matb-fac-standard", version="1.0.0", label_es="Suite MATB-FAC estándar",
                    status="published", settings_json=_canonical(DEFAULT_PROFILES), sha256=_sha(DEFAULT_PROFILES), published_at=_utcnow(),
                ))
            if db.exec(select(OpenMatbInstructionProtocol).where(OpenMatbInstructionProtocol.protocol_id == "matb-fac-es-419", OpenMatbInstructionProtocol.version == "1.0.0")).first() is None:
                db.add(OpenMatbInstructionProtocol(
                    protocol_id="matb-fac-es-419", version="1.0.0", locale="es-419", status="published",
                    content_json=_canonical(DEFAULT_INSTRUCTIONS), sha256=_sha(DEFAULT_INSTRUCTIONS), published_at=_utcnow(),
                ))
            db.commit()

    def _mark_interrupted(self) -> None:
        with Session(self.engine) as db:
            rows = db.exec(select(OpenMatbSuiteSession).where(OpenMatbSuiteSession.lifecycle.in_(("STARTING", "RUNNING", "PAUSED")))).all()
            for row in rows:
                row.lifecycle = "INTERRUPTED"
                row.active_pid = None
                row.last_error = "backend_restart"
                db.add(row)
            db.commit()

    def readiness(self) -> OpenMatbReadiness:
        runtime_dependencies = False
        if self.python_executable.is_file():
            try:
                probe = subprocess.run(
                    [str(self.python_executable), "-c", "import pyglet, rstr"],
                    cwd=self.openmatb_root,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                    check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                runtime_dependencies = probe.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                runtime_dependencies = False
        checks = {
            "python": self.python_executable.is_file(),
            "runtime_dependencies": runtime_dependencies,
            "openmatb": (self.openmatb_root / "main.py").is_file(),
            "questionnaires_es": all((self.openmatb_root / "includes" / "questionnaires" / name).is_file() for name in (ISA_QUESTIONNAIRE_ES, NASATLX_QUESTIONNAIRE_ES, BEDFORD_QUESTIONNAIRE_ES)),
            "graphical_display": platform.system() == "Windows" or bool(os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY")),
        }
        warnings = []
        if not checks["runtime_dependencies"]:
            warnings.append("OpenMATB Python dependencies are missing or cannot be imported. Run the Windows preparation launcher again.")
        if not checks["graphical_display"]:
            warnings.append("Linux requires an active X11 or Wayland display for the participant window.")
        return OpenMatbReadiness(
            ready=all(checks.values()), platform=platform.system(), python_executable=str(self.python_executable),
            openmatb_entrypoint=str(self.openmatb_root / "main.py"), display_index_default=1, checks=checks, warnings=warnings,
        )

    def list_presets(self) -> list[PresetSetView]:
        with Session(self.engine) as db:
            rows = db.exec(select(OpenMatbPresetSet).order_by(OpenMatbPresetSet.created_at)).all()
            return [self._preset_view(row) for row in rows]

    def clone_preset(self, source_id: str, source_version: str, request: ClonePresetRequest) -> PresetSetView:
        with Session(self.engine) as db:
            source = db.exec(select(OpenMatbPresetSet).where(OpenMatbPresetSet.preset_id == source_id, OpenMatbPresetSet.version == source_version)).first()
            if source is None:
                raise OpenMatbRuntimeError("preset_not_found")
            duplicate = db.exec(select(OpenMatbPresetSet).where(OpenMatbPresetSet.preset_id == request.preset_id, OpenMatbPresetSet.version == request.version)).first()
            if duplicate is not None:
                raise OpenMatbRuntimeError("preset_already_exists")
            row = OpenMatbPresetSet(
                preset_id=request.preset_id, version=request.version, label_es=request.label_es,
                status="draft", settings_json=source.settings_json, sha256=source.sha256,
            )
            db.add(row); db.commit(); db.refresh(row)
            return self._preset_view(row)

    def update_preset(self, preset_id: str, version: str, request: UpdatePresetRequest) -> PresetSetView:
        payload = {key: value.model_dump() for key, value in request.profiles.items()}
        with Session(self.engine) as db:
            row = db.exec(select(OpenMatbPresetSet).where(OpenMatbPresetSet.preset_id == preset_id, OpenMatbPresetSet.version == version)).first()
            if row is None:
                raise OpenMatbRuntimeError("preset_not_found")
            if row.status != "draft":
                raise OpenMatbRuntimeError("published_configuration_immutable")
            row.settings_json = _canonical(payload); row.sha256 = _sha(payload)
            db.add(row); db.commit(); db.refresh(row)
            return self._preset_view(row)

    def publish_preset(self, preset_id: str, version: str) -> PresetSetView:
        with Session(self.engine) as db:
            row = db.exec(select(OpenMatbPresetSet).where(OpenMatbPresetSet.preset_id == preset_id, OpenMatbPresetSet.version == version)).first()
            if row is None:
                raise OpenMatbRuntimeError("preset_not_found")
            settings = json.loads(row.settings_json)
            ordered = [settings[name] for name in ("LOW", "MEDIUM", "HIGH")]
            if not (
                ordered[0]["difficulty"] < ordered[1]["difficulty"] < ordered[2]["difficulty"]
                and ordered[0]["track_target_proportion"] > ordered[1]["track_target_proportion"] > ordered[2]["track_target_proportion"]
                and ordered[0]["resman_loss_per_min"] < ordered[1]["resman_loss_per_min"] < ordered[2]["resman_loss_per_min"]
                and ordered[0]["isa_probe_interval_sec"] >= ordered[1]["isa_probe_interval_sec"] >= ordered[2]["isa_probe_interval_sec"]
            ):
                raise OpenMatbRuntimeError("preset_workload_order_invalid")
            row.status = "published"; row.published_at = _utcnow()
            db.add(row); db.commit(); db.refresh(row)
            return self._preset_view(row)

    @staticmethod
    def _preset_view(row: OpenMatbPresetSet) -> PresetSetView:
        settings = json.loads(row.settings_json)
        return PresetSetView(
            preset_id=row.preset_id, version=row.version, label_es=row.label_es, status=row.status,
            sha256=row.sha256, profiles={key: ProfileSettings.model_validate(value) for key, value in settings.items()},
        )

    def list_instructions(self) -> list[InstructionProtocolView]:
        with Session(self.engine) as db:
            rows = db.exec(select(OpenMatbInstructionProtocol).order_by(OpenMatbInstructionProtocol.created_at)).all()
            return [self._instruction_view(row) for row in rows]

    def clone_instructions(self, source_id: str, source_version: str, request: CloneInstructionRequest) -> InstructionProtocolView:
        with Session(self.engine) as db:
            source = db.exec(select(OpenMatbInstructionProtocol).where(OpenMatbInstructionProtocol.protocol_id == source_id, OpenMatbInstructionProtocol.version == source_version)).first()
            if source is None:
                raise OpenMatbRuntimeError("instruction_protocol_not_found")
            duplicate = db.exec(select(OpenMatbInstructionProtocol).where(OpenMatbInstructionProtocol.protocol_id == request.protocol_id, OpenMatbInstructionProtocol.version == request.version)).first()
            if duplicate is not None:
                raise OpenMatbRuntimeError("instruction_protocol_already_exists")
            row = OpenMatbInstructionProtocol(
                protocol_id=request.protocol_id, version=request.version, locale=source.locale,
                status="draft", content_json=source.content_json, sha256=source.sha256,
            )
            db.add(row); db.commit(); db.refresh(row)
            return self._instruction_view(row)

    def update_instructions(self, protocol_id: str, version: str, request: UpdateInstructionRequest) -> InstructionProtocolView:
        payload = request.model_dump()
        with Session(self.engine) as db:
            row = db.exec(select(OpenMatbInstructionProtocol).where(OpenMatbInstructionProtocol.protocol_id == protocol_id, OpenMatbInstructionProtocol.version == version)).first()
            if row is None:
                raise OpenMatbRuntimeError("instruction_protocol_not_found")
            if row.status != "draft":
                raise OpenMatbRuntimeError("published_configuration_immutable")
            row.content_json = _canonical(payload); row.sha256 = _sha(payload)
            db.add(row); db.commit(); db.refresh(row)
            return self._instruction_view(row)

    def publish_instructions(self, protocol_id: str, version: str) -> InstructionProtocolView:
        with Session(self.engine) as db:
            row = db.exec(select(OpenMatbInstructionProtocol).where(OpenMatbInstructionProtocol.protocol_id == protocol_id, OpenMatbInstructionProtocol.version == version)).first()
            if row is None:
                raise OpenMatbRuntimeError("instruction_protocol_not_found")
            row.status = "published"; row.published_at = _utcnow()
            db.add(row); db.commit(); db.refresh(row)
            return self._instruction_view(row)

    @staticmethod
    def _instruction_view(row: OpenMatbInstructionProtocol) -> InstructionProtocolView:
        content = json.loads(row.content_json)
        visit_instructions = content.get("visit_instructions") or DEFAULT_INSTRUCTIONS["visit_instructions"]
        return InstructionProtocolView(
            protocol_id=row.protocol_id, version=row.version, locale=row.locale, status=row.status,
            sha256=row.sha256, title=content["title"], steps=content["steps"], task_instructions=content["task_instructions"],
            visit_instructions=visit_instructions,
        )

    async def create_session(self, request: CreateOpenMatbSession) -> PreparedOpenMatbSession:
        async with self._lock:
            with Session(self.engine) as db:
                active = db.exec(select(OpenMatbSuiteSession).where(OpenMatbSuiteSession.lifecycle.in_(("INSTRUCTIONS", "READY", "STARTING", "RUNNING", "PAUSED", "AWAITING_SCALE", "BETWEEN_BLOCKS")))).first()
                if active is not None:
                    raise OpenMatbRuntimeError("openmatb_active_session")
                participant = db.get(Participant, request.participant_id)
                if participant is None:
                    raise OpenMatbRuntimeError("participant_not_found")
                visit = db.exec(select(Visit).where(Visit.participant_id == request.participant_id, Visit.visit_ordinal == request.visit_ordinal)).first()
                if visit is None or visit.id is None:
                    raise OpenMatbRuntimeError("visit_not_found")
                preset = db.exec(select(OpenMatbPresetSet).where(OpenMatbPresetSet.preset_id == request.preset_id, OpenMatbPresetSet.version == request.preset_version, OpenMatbPresetSet.status == "published")).first()
                instructions = db.exec(select(OpenMatbInstructionProtocol).where(OpenMatbInstructionProtocol.protocol_id == request.instruction_protocol_id, OpenMatbInstructionProtocol.version == request.instruction_version, OpenMatbInstructionProtocol.status == "published")).first()
                if preset is None or instructions is None:
                    raise OpenMatbRuntimeError("published_configuration_not_found")
                session_id = str(uuid4())
                run_dir = self.artifact_root / session_id
                scenario_dir = run_dir / "scenarios"
                session_dir = run_dir / "sessions"
                scenario_dir.mkdir(parents=True, exist_ok=False)
                session_dir.mkdir(parents=True, exist_ok=False)
                settings = json.loads(preset.settings_json)
                order = ["PRACTICE", *(level.value.upper() for level in block_order_for_participant(request.participant_id))]
                source_commit, source_dirty = detect_generator_source_provenance(self.repo_root)
                paths: dict[str, str] = {}
                for index, block in enumerate(order):
                    level = WorkloadLevel.LOW if block == "PRACTICE" else WorkloadLevel(block.lower())
                    profile = settings[block]
                    text = build_block_scenario(
                        level=level, block_duration_sec=int(profile["duration_seconds"]), seed=42 + request.visit_ordinal * 10 + index,
                        isa_questionnaire=ISA_QUESTIONNAIRE_ES, include_nasatlx=False, include_bedford=False,
                        workload_settings=profile,
                    )
                    path = scenario_dir / f"{index}_{block}.txt"
                    _write_scenario_with_manifest(
                        path, text, level=level, block_duration_sec=int(profile["duration_seconds"]),
                        seed=42 + request.visit_ordinal * 10 + index, isa_questionnaire=ISA_QUESTIONNAIRE_ES,
                        nasatlx_questionnaire=NASATLX_QUESTIONNAIRE_ES, bedford_questionnaire=BEDFORD_QUESTIONNAIRE_ES,
                        include_nasatlx=False, include_bedford=False, participant_id=request.participant_id,
                        block_num=index + 1, visit_ordinal=request.visit_ordinal, source_commit=source_commit,
                        source_dirty=source_dirty, workload_settings=profile, profile_name=block,
                        visual_theme=request.visual_theme,
                    )
                    paths[block] = str(path)
                controller_lease = secrets.token_urlsafe(32)
                participant_token = secrets.token_urlsafe(32)
                row = OpenMatbSuiteSession(
                    id=session_id, participant_id=request.participant_id, visit_id=visit.id, visit_ordinal=request.visit_ordinal,
                    preset_id=preset.preset_id, preset_version=preset.version, preset_sha256=preset.sha256,
                    instruction_protocol_id=instructions.protocol_id, instruction_version=instructions.version,
                    instruction_sha256=instructions.sha256, visual_theme=request.visual_theme,
                    display_index=request.display_index,
                    block_order_json=_canonical(order), scenario_paths_json=_canonical(paths),
                    controller_lease_hash=_token_hash(controller_lease), participant_token_hash=_token_hash(participant_token),
                    artifact_root=str(run_dir),
                )
                db.add(row)
                db.commit()
                return PreparedOpenMatbSession(session=self._view(db, row), controller_lease=controller_lease, participant_token=participant_token)

    def session_view(self, session_id: str) -> OpenMatbSessionView:
        with Session(self.engine) as db:
            row = db.get(OpenMatbSuiteSession, session_id)
            if row is None:
                raise OpenMatbRuntimeError("openmatb_session_not_found")
            return self._view(db, row)

    def _view(self, db: Session, row: OpenMatbSuiteSession) -> OpenMatbSessionView:
        visit = db.get(Visit, row.visit_id)
        instruction = db.exec(select(OpenMatbInstructionProtocol).where(OpenMatbInstructionProtocol.protocol_id == row.instruction_protocol_id, OpenMatbInstructionProtocol.version == row.instruction_version)).one()
        protocol_visit = next(item for item in selected_protocol().visits if item.ordinal == row.visit_ordinal)
        instruction_view = self._instruction_view(instruction)
        order = json.loads(row.block_order_json)
        active = order[row.current_block_index] if row.current_block_index < len(order) and row.lifecycle in {"STARTING", "RUNNING", "PAUSED", "AWAITING_SCALE"} else None
        return OpenMatbSessionView(
            id=row.id, participant_id=row.participant_id, visit_ordinal=row.visit_ordinal,
            visit_code=protocol_visit.code, scheduled_day=visit.scheduled_day if visit else protocol_visit.scheduled_day,
            lifecycle=row.lifecycle, block_order=order, current_block_index=row.current_block_index, active_block=active,
            preset_id=row.preset_id, preset_version=row.preset_version, preset_sha256=row.preset_sha256,
            instruction_protocol=instruction_view,
            visit_instruction=instruction_view.visit_instructions.get(protocol_visit.code, instruction_view.visit_instructions["DEFAULT"]),
            visual_theme=row.visual_theme, display_index=row.display_index,
            scores=json.loads(row.scores_json), active_pid=row.active_pid, last_error=row.last_error,
            created_at=row.created_at, started_at=row.started_at, finished_at=row.finished_at,
        )

    def acknowledge_instructions(self, session_id: str, participant_token: str) -> OpenMatbSessionView:
        with Session(self.engine) as db:
            row = self._participant_row(db, session_id, participant_token)
            if row.lifecycle != "INSTRUCTIONS":
                raise OpenMatbRuntimeError("openmatb_invalid_transition")
            row.lifecycle = "READY"
            db.add(row); db.commit(); db.refresh(row)
            return self._view(db, row)

    async def start_block(self, session_id: str, lease: str) -> OpenMatbSessionView:
        async with self._lock:
            with Session(self.engine) as db:
                row = self._controller_row(db, session_id, lease)
                if row.lifecycle not in {"READY", "BETWEEN_BLOCKS"}:
                    raise OpenMatbRuntimeError("openmatb_invalid_transition")
                order = json.loads(row.block_order_json)
                if row.current_block_index >= len(order):
                    raise OpenMatbRuntimeError("openmatb_suite_complete")
                block = order[row.current_block_index]
                scenario = Path(json.loads(row.scenario_paths_json)[block]).resolve()
                if scenario.parent != Path(row.artifact_root).resolve() / "scenarios" or not scenario.is_file():
                    raise OpenMatbRuntimeError("openmatb_scenario_missing")
                command = [
                    str(self.python_executable), str(self.openmatb_root / "main.py"), "--scenario", str(scenario),
                    "--session-dir", str(Path(row.artifact_root) / "sessions" / block), "--language", "es_CO",
                    "--visual-theme", row.visual_theme,
                    "--display-index", str(row.display_index), "--control-stdio",
                ]
                session_path = Path(row.artifact_root) / "sessions" / block
                session_path.mkdir(parents=True, exist_ok=True)
                kwargs: dict[str, Any] = {"cwd": str(self.openmatb_root), "stdin": asyncio.subprocess.PIPE, "stdout": asyncio.subprocess.PIPE, "stderr": asyncio.subprocess.PIPE}
                if os.name == "nt":
                    kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                else:
                    kwargs["start_new_session"] = True
                try:
                    process = await asyncio.create_subprocess_exec(*command, **kwargs)
                except OSError as exc:
                    row.lifecycle = "FAILED"; row.active_pid = None; row.last_error = "openmatb_launch_failed"
                    db.add(row); db.commit()
                    raise OpenMatbRuntimeError("openmatb_launch_failed") from exc
                try:
                    windows_job = _WindowsJob(process.pid) if os.name == "nt" else None
                except OSError as exc:
                    process.terminate()
                    await process.wait()
                    row.lifecycle = "FAILED"; row.active_pid = None; row.last_error = "openmatb_job_assignment_failed"
                    db.add(row); db.commit()
                    raise OpenMatbRuntimeError("openmatb_job_assignment_failed") from exc
                handle = _ProcessHandle(session_id=session_id, block=block, process=process, windows_job=windows_job)
                self._handles[session_id] = handle
                row.lifecycle = "STARTING"; row.active_pid = process.pid; row.started_at = row.started_at or _utcnow(); row.last_error = None
                db.add(row); db.commit()
                handle.monitor = asyncio.create_task(self._monitor(handle))
            ready_wait = asyncio.create_task(handle.ready.wait())
            exited_wait = asyncio.create_task(handle.exited.wait())
            try:
                done, _ = await asyncio.wait(
                    {ready_wait, exited_wait}, timeout=20, return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    await self._terminate(handle)
                    self._set_failure(session_id, "openmatb_ready_timeout")
                    raise OpenMatbRuntimeError("openmatb_ready_timeout")
                if handle.exited.is_set() and not handle.ready.is_set():
                    failure = self._launch_failure_code(handle)
                    self._set_failure(session_id, failure)
                    raise OpenMatbRuntimeError(failure)
                if handle.process.returncode not in {None, 0}:
                    failure = self._launch_failure_code(handle)
                    self._set_failure(session_id, failure)
                    raise OpenMatbRuntimeError(failure)
            finally:
                for waiter in (ready_wait, exited_wait):
                    if not waiter.done():
                        waiter.cancel()
                await asyncio.gather(ready_wait, exited_wait, return_exceptions=True)
            with Session(self.engine) as db:
                row = db.get(OpenMatbSuiteSession, session_id)
                assert row is not None
                row.lifecycle = "RUNNING"; db.add(row); db.commit(); db.refresh(row)
                return self._view(db, row)

    async def _monitor(self, handle: _ProcessHandle) -> None:
        async def stdout_reader() -> None:
            assert handle.process.stdout is not None
            while line := await handle.process.stdout.readline():
                try:
                    event = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if event.get("event") == "ready":
                    raw = event.get("session_csv")
                    handle.session_csv = Path(raw).resolve() if isinstance(raw, str) else None
                    handle.ready.set()
                elif event.get("event") == "finished":
                    raw = event.get("session_csv")
                    handle.session_csv = Path(raw).resolve() if isinstance(raw, str) else handle.session_csv

        async def stderr_reader() -> None:
            assert handle.process.stderr is not None
            while line := await handle.process.stderr.readline():
                handle.stderr.append(line.decode("utf-8", errors="replace").strip())
                del handle.stderr[:-20]

        try:
            await asyncio.gather(stdout_reader(), stderr_reader(), handle.process.wait())
        finally:
            handle.exited.set()
            if handle.windows_job is not None:
                handle.windows_job.close()
        async with self._lock:
            with Session(self.engine) as db:
                row = db.get(OpenMatbSuiteSession, handle.session_id)
                if row is None or row.lifecycle == "ABORTED":
                    self._handles.pop(handle.session_id, None)
                    return
                row.active_pid = None
                if not handle.ready.is_set() or handle.process.returncode != 0:
                    row.lifecycle = "FAILED"
                    row.last_error = self._launch_failure_code(handle)
                else:
                    row.active_session_csv = str(handle.session_csv) if handle.session_csv else None
                    if handle.block == "PRACTICE":
                        row.current_block_index += 1
                        row.lifecycle = "BETWEEN_BLOCKS"
                    else:
                        row.lifecycle = "AWAITING_SCALE"
                db.add(row); db.commit()
            self._handles.pop(handle.session_id, None)

    @staticmethod
    def _launch_failure_code(handle: _ProcessHandle) -> str:
        diagnostic = "\n".join(handle.stderr).lower()
        if "no module named" in diagnostic or "modulenotfounderror" in diagnostic:
            return "openmatb_dependency_missing"
        return "openmatb_launch_failed"

    async def pause(self, session_id: str, lease: str) -> OpenMatbSessionView:
        return await self._command(session_id, lease, "pause", "PAUSED", {"RUNNING"})

    async def resume(self, session_id: str, lease: str) -> OpenMatbSessionView:
        return await self._command(session_id, lease, "resume", "RUNNING", {"PAUSED"})

    def repeat_practice(self, session_id: str, lease: str) -> OpenMatbSessionView:
        with Session(self.engine) as db:
            row = self._controller_row(db, session_id, lease)
            if row.lifecycle != "BETWEEN_BLOCKS" or row.current_block_index != 1 or json.loads(row.scores_json):
                raise OpenMatbRuntimeError("openmatb_practice_cannot_repeat")
            row.current_block_index = 0
            row.lifecycle = "READY"
            row.active_session_csv = None
            db.add(row); db.commit(); db.refresh(row)
            return self._view(db, row)

    async def _command(self, session_id: str, lease: str, command: str, lifecycle: str, allowed: set[str]) -> OpenMatbSessionView:
        async with self._lock:
            with Session(self.engine) as db:
                row = self._controller_row(db, session_id, lease)
                if row.lifecycle not in allowed:
                    raise OpenMatbRuntimeError("openmatb_invalid_transition")
                handle = self._handles.get(session_id)
                if handle is None or handle.process.stdin is None:
                    raise OpenMatbRuntimeError("openmatb_process_unavailable")
                handle.process.stdin.write((_canonical({"command": command}) + "\n").encode("utf-8"))
                await handle.process.stdin.drain()
                row.lifecycle = lifecycle; db.add(row); db.commit(); db.refresh(row)
                return self._view(db, row)

    async def abort(self, session_id: str, lease: str, reason: str) -> OpenMatbSessionView:
        async with self._lock:
            with Session(self.engine) as db:
                row = self._controller_row(db, session_id, lease)
                if row.lifecycle in {"COMPLETE", "ABORTED"}:
                    raise OpenMatbRuntimeError("openmatb_invalid_transition")
                handle = self._handles.get(session_id)
                if handle is not None:
                    await self._terminate(handle)
                row.lifecycle = "ABORTED"; row.active_pid = None; row.last_error = reason; row.finished_at = _utcnow()
                db.add(row); db.commit(); db.refresh(row)
                self._handles.pop(session_id, None)
                return self._view(db, row)

    async def _terminate(self, handle: _ProcessHandle) -> None:
        if handle.process.returncode is not None:
            return
        if os.name != "nt":
            try:
                os.killpg(handle.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        else:
            handle.process.terminate()
        try:
            await asyncio.wait_for(handle.process.wait(), timeout=5)
        except TimeoutError:
            if os.name != "nt":
                try:
                    os.killpg(handle.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                handle.process.kill()
            await handle.process.wait()
        if handle.windows_job is not None:
            handle.windows_job.close()

    def submit_scale(self, session_id: str, participant_token: str, request: WorkloadScaleRequest) -> OpenMatbSessionView:
        with Session(self.engine) as db:
            row = self._participant_row(db, session_id, participant_token)
            if row.lifecycle != "AWAITING_SCALE":
                raise OpenMatbRuntimeError("openmatb_scale_not_expected")
            order = json.loads(row.block_order_json)
            block = order[row.current_block_index]
            scores = json.loads(row.scores_json)
            scores[block] = {
                "instrument_version": "MATB-FAC-WORKLOAD-1.0",
                "locale": "es-419",
                "nasa_tlx": request.nasa_tlx,
                "rtlx_mean_0_100": sum(request.nasa_tlx.values()) / 6,
                "bedford": request.bedford,
                "bedford_status": "exploratory_translation_not_locally_validated",
            }
            row.scores_json = _canonical(scores)
            self._persist_scale_sidecar(row, block, scores[block])
            self._ingest_completed_block(db, row, block, request)
            row.current_block_index += 1
            row.lifecycle = "COMPLETE" if row.current_block_index >= len(order) else "BETWEEN_BLOCKS"
            if row.lifecycle == "COMPLETE":
                row.finished_at = _utcnow()
                visit = db.get(Visit, row.visit_id)
                if visit is not None:
                    visit.status = "complete"; db.add(visit)
            db.add(row); db.commit(); db.refresh(row)
            return self._view(db, row)

    @staticmethod
    def _persist_scale_sidecar(row: OpenMatbSuiteSession, block: str, payload: object) -> None:
        path = Path(row.artifact_root) / "scales" / f"{block}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_canonical(payload) + "\n", encoding="utf-8", newline="\n")

    def _ingest_completed_block(self, db: Session, row: OpenMatbSuiteSession, block: str, request: WorkloadScaleRequest) -> None:
        if not row.active_session_csv:
            return
        csv_path = Path(row.active_session_csv).resolve()
        session_root = (Path(row.artifact_root) / "sessions").resolve()
        if session_root not in csv_path.parents or not csv_path.is_file():
            row.last_error = "session_csv_outside_artifact_root"
            return
        content = csv_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        if not lines:
            row.last_error = "session_csv_empty"
            return
        timestamp = ProfileSettings.model_validate(
            json.loads(self._preset_row(row).settings_json)[block]
        ).duration_seconds
        additions = []
        labels = {
            "mental_demand": "Mental demand", "physical_demand": "Physical demand", "temporal_demand": "Temporal demand",
            "performance": "Performance", "effort": "Effort", "frustration": "Frustration",
        }
        for key, label in labels.items():
            additions.append(f"{timestamp},{timestamp},performance,genericscales,{label},{request.nasa_tlx[key] / 10:g}")
        additions.append(f"{timestamp},{timestamp},performance,genericscales,Bedford,{request.bedford}")
        merged = ("\n".join([*lines, *additions]) + "\n").encode("utf-8")
        manifest_path = Path(json.loads(row.scenario_paths_json)[block] + ".manifest.json")
        try:
            ingest_csv(
                db, content=merged, filename=csv_path.name, participant_id=row.participant_id,
                visit_ordinal=row.visit_ordinal, workload_level=block, overwrite=False,
                manifest_content=manifest_path.read_bytes() if manifest_path.is_file() else None,
                manifest_filename=manifest_path.name if manifest_path.is_file() else None,
            )
        except IngestionError as exc:
            row.last_error = f"automatic_ingest: {exc}"[:2000]

    def _preset_row(self, row: OpenMatbSuiteSession) -> OpenMatbPresetSet:
        with Session(self.engine) as db:
            preset = db.exec(select(OpenMatbPresetSet).where(OpenMatbPresetSet.preset_id == row.preset_id, OpenMatbPresetSet.version == row.preset_version)).one()
            db.expunge(preset)
            return preset

    def _controller_row(self, db: Session, session_id: str, lease: str) -> OpenMatbSuiteSession:
        row = db.get(OpenMatbSuiteSession, session_id)
        if row is None:
            raise OpenMatbRuntimeError("openmatb_session_not_found")
        if not secrets.compare_digest(row.controller_lease_hash, _token_hash(lease)):
            raise OpenMatbRuntimeError("openmatb_invalid_lease")
        return row

    def _participant_row(self, db: Session, session_id: str, token: str) -> OpenMatbSuiteSession:
        row = db.get(OpenMatbSuiteSession, session_id)
        if row is None:
            raise OpenMatbRuntimeError("openmatb_session_not_found")
        if not secrets.compare_digest(row.participant_token_hash, _token_hash(token)):
            raise OpenMatbRuntimeError("openmatb_invalid_participant_token")
        return row

    def _set_failure(self, session_id: str, code: str) -> None:
        with Session(self.engine) as db:
            row = db.get(OpenMatbSuiteSession, session_id)
            if row is not None:
                row.lifecycle = "FAILED"; row.active_pid = None; row.last_error = code; db.add(row); db.commit()

    async def shutdown(self) -> None:
        async with self._lock:
            for handle in list(self._handles.values()):
                await self._terminate(handle)
                self._set_failure(handle.session_id, "backend_shutdown")
            self._handles.clear()
    UpdateInstructionRequest,
    UpdatePresetRequest,
