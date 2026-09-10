"""Supervise native OpenMATB processes from the local research console."""

from __future__ import annotations

from fastapi import HTTPException
from app.purpose_service import declare_acquisition
from app.study_native import selected_task_source

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
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from aircraft_monitor.research.protocol import WorkloadLevel
from app.ingestion import IngestionError, ingest_csv
from app.native_process_guard import process_alive as _process_alive
from app.models import Participant, Visit
from app.openmatb_models import (
    OpenMatbInstructionProtocol,
    OpenMatbPresetSet,
    OpenMatbSuiteSession,
    OpenMatbVisualProfile,
    OpenMatbBlockAttempt,
)
from app.openmatb_records import OpenMatbRecords
from app.openmatb_schemas import (
    CloneInstructionRequest,
    ClonePresetRequest,
    CloneVisualProfileRequest,
    CreateOpenMatbSession,
    ImportVisualProfileRequest,
    InstructionProtocolView,
    OpenMatbReadiness,
    OpenMatbSessionView,
    OpenMatbVisualProfileView,
    PreparedOpenMatbSession,
    PresetSetView,
    ProfileSettings,
    PublishVisualProfileRequest,
    UpdateInstructionRequest,
    UpdatePresetRequest,
    UpdateVisualProfileRequest,
    VisualProfileDocument,
    VisualProfilePreviewRequest,
    VisualProfilePreviewView,
    VisualProfileValidation,
    WorkloadScaleRequest,
)
from app.study_protocol import selected_protocol
from matb_integration.openmatb_visual_profiles import (
    VisualProfileValidationError,
    assess_visual_profile,
    clone_profile_identity,
    load_visual_profile,
    profile_sha256,
    validate_visual_profile,
)
from matb_integration.openmatb_visual_profiles import (
    canonical_json as canonical_profile_json,
)
from matb_integration.scenario_builder import (
    BEDFORD_QUESTIONNAIRE,
    ISA_QUESTIONNAIRE,
    NASATLX_QUESTIONNAIRE,
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

ENGLISH_INSTRUCTIONS = {
    "title": "Instructions for your MATB-FAC session",
    "steps": [
        "Confirm your participant code and visit.",
        "Adjust your chair and check the display, sound, mouse, keyboard or joystick.",
        "Read the four task instructions, then practice the controls.",
        "During each block, monitor all four tasks and respond with the indicated controls.",
        "After each study block, answer the workload questions about that block.",
        "Wait for saving confirmation before continuing or closing the application.",
    ],
    "task_instructions": {
        "TRACK": "Tracking: keep the cursor inside the target using the configured joystick or mouse.",
        "COMM": "Communications: listen to messages and respond only when they address your callsign.",
        "SYSMON": "System monitoring: detect and reset lights or gauges that enter a fault state.",
        "RESMAN": "Resource management: operate the pumps to keep fuel levels close to their targets.",
    },
    "visit_instructions": {"DEFAULT": "Complete practice first. Study blocks follow the order assigned by the application."},
}

DEFAULT_VISUAL_PROFILE = ("matb-fac-modern", "1.0.0")
LEGACY_THEME_PROFILE = {
    "classic": ("classic", "1.0.0"),
    "cockpit": ("cockpit", "1.0.0"),
    "fac_modern": DEFAULT_VISUAL_PROFILE,
}
BUNDLED_VISUAL_PROFILE_IDENTITIES = frozenset(LEGACY_THEME_PROFILE.values())


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
    block_instance_id: str | None = None


@dataclass
class _PreviewState:
    lifecycle: str = "IDLE"
    profile_id: str | None = None
    profile_version: str | None = None
    profile_sha256: str | None = None
    artifact_root: Path | None = None
    handle: _ProcessHandle | None = None
    last_error: str | None = None


class OpenMatbManager:
    def __init__(self, *, engine, repo_root: Path, artifact_root: Path, python_executable: Path | None = None) -> None:
        self.engine = engine
        self.repo_root = repo_root.resolve()
        self.openmatb_root = self.repo_root / "openmatb"
        self.artifact_root = artifact_root.resolve()
        self.preview_root = self.artifact_root.parent / "openmatb-preview"
        self.python_executable = (python_executable or Path(sys.executable)).resolve()
        self._lock = asyncio.Lock()
        self._scale_lock = threading.Lock()
        self._handles: dict[str, _ProcessHandle] = {}
        self._preview = _PreviewState()
        self.records = OpenMatbRecords(engine, self.artifact_root)
        self._evidence_task: asyncio.Task[None] | None = None
        self._processing_evidence = False
        self._closing = False
        self._seed_defaults()
        self._seed_english_instructions()
        self._mark_interrupted()
        self.records.recover()

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
            for bundled_name in ("classic", "cockpit", "fac_modern"):
                payload = load_visual_profile(self.openmatb_root / "themes" / f"{bundled_name}.json")
                existing = db.exec(
                    select(OpenMatbVisualProfile).where(
                        OpenMatbVisualProfile.profile_id == payload["profile_id"],
                        OpenMatbVisualProfile.version == payload["version"],
                    )
                ).first()
                if existing is not None:
                    if existing.sha256 != profile_sha256(payload):
                        raise RuntimeError(
                            "bundled OpenMATB visual-profile identity collides with different stored content"
                        )
                    continue
                assessment = assess_visual_profile(payload)
                acknowledgements = sorted(issue["code"] for issue in assessment["warnings"])
                db.add(
                    OpenMatbVisualProfile(
                        profile_id=payload["profile_id"],
                        version=payload["version"],
                        label=payload["label"],
                        status="published",
                        schema_version=payload["schema_version"],
                        payload_json=canonical_profile_json(payload),
                        sha256=profile_sha256(payload),
                        validation_json=_canonical(assessment),
                        warning_acknowledgements_json=_canonical(acknowledgements),
                        published_at=_utcnow(),
                    )
                )
            db.commit()

    def _seed_english_instructions(self) -> None:
        with Session(self.engine) as db:
            existing = db.exec(select(OpenMatbInstructionProtocol).where(
                OpenMatbInstructionProtocol.protocol_id == "matb-fac-en",
                OpenMatbInstructionProtocol.version == "1.0.0",
            )).first()
            if existing is None:
                db.add(OpenMatbInstructionProtocol(
                    protocol_id="matb-fac-en", version="1.0.0", locale="en", status="published",
                    content_json=_canonical(ENGLISH_INSTRUCTIONS), sha256=_sha(ENGLISH_INSTRUCTIONS), published_at=_utcnow(),
                ))
                db.commit()

    def _mark_interrupted(self) -> None:
        with Session(self.engine) as db:
            rows = db.exec(select(OpenMatbSuiteSession).where(OpenMatbSuiteSession.lifecycle.in_(("STARTING", "RUNNING", "PAUSED")))).all()
            for row in rows:
                from app.study_admission import sync_runtime_attempt
                sync_runtime_attempt(db, row, state='interrupted')
                row.lifecycle = "INTERRUPTED"
                row.recovery_pid = row.active_pid
                row.active_pid = None
                row.last_error = "backend_restart"
                row.finished_at = _utcnow()
                db.add(row)
            db.commit()

    def _native_recovery_required(self) -> bool:
        pending = False
        with Session(self.engine) as db:
            for row in db.exec(select(OpenMatbSuiteSession).where(OpenMatbSuiteSession.recovery_pid.is_not(None))):
                if _process_alive(row.recovery_pid):
                    pending = True
                else:
                    row.recovery_pid = None
                    db.add(row)
            db.commit()
        return pending

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
            "native_process_clear": not self._native_recovery_required(),
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

    def displays(self) -> list[dict]:
        try:
            result = subprocess.run([str(self.python_executable), "-m", "matb_integration.openmatb_displays"],
                cwd=self.repo_root, stdin=subprocess.DEVNULL, capture_output=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            rows = json.loads(result.stdout) if result.returncode == 0 else None
            if not isinstance(rows, list) or not rows:
                raise ValueError("no_displays")
            if any(not isinstance(row, dict) or row.get("index") != index
                   or not all(type(row.get(key)) is int for key in ("width", "height", "x", "y"))
                   or row["width"] <= 0 or row["height"] <= 0 for index, row in enumerate(rows)):
                raise ValueError("invalid_displays")
            return rows[:16]
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            raise OpenMatbRuntimeError("openmatb_display_discovery_failed") from exc

    def _validate_display(self, index: int) -> None:
        if index not in {row["index"] for row in self.displays()}:
            raise OpenMatbRuntimeError("openmatb_display_unavailable")

    def receipt(self, session_id: str) -> dict:
        with Session(self.engine) as db:
            row = db.get(OpenMatbSuiteSession, session_id)
            if row is None:
                raise OpenMatbRuntimeError("openmatb_session_not_found")
            return self.records.receipt(db, row)

    def schedule_evidence_processing(self) -> None:
        if self._closing or self._evidence_task is not None and not self._evidence_task.done():
            return
        try:
            self._evidence_task = asyncio.get_running_loop().create_task(self._wait_and_process_evidence())
        except RuntimeError:
            # Synchronous callers still leave a durable queue for startup.
            pass

    async def _wait_and_process_evidence(self) -> None:
        while not self._closing and self._native_recovery_required():
            await asyncio.sleep(1)
        if not self._closing:
            await self._process_evidence()

    async def _process_evidence(self) -> None:
        while not self._closing:
            async with self._lock:
                if self._handles or self._preview.handle is not None or self._native_recovery_required():
                    return
                pending = self.records.pending()
                if not pending:
                    return
                self._processing_evidence = True
            try:
                await asyncio.to_thread(self.records.process, pending[0])
            finally:
                self._processing_evidence = False

    async def retry_evidence(self, session_id: str, attempt_id: str, lease: str) -> dict:
        async with self._lock:
            with Session(self.engine) as db:
                suite = self._controller_row(db, session_id, lease)
                attempt = db.get(OpenMatbBlockAttempt, attempt_id)
                if attempt is None or attempt.session_id != suite.id:
                    raise OpenMatbRuntimeError("openmatb_block_mismatch")
                if suite.lifecycle not in {"COMPLETE", "ABORTED", "FAILED", "INTERRUPTED"}:
                    raise OpenMatbRuntimeError("openmatb_evidence_wait_for_completion")
                if attempt.evidence_status in {"failed", "unavailable"}:
                    attempt.evidence_status = "queued"
                    attempt.evidence_error = None
                    db.add(attempt)
                    db.commit()
        self.schedule_evidence_processing()
        return self.receipt(session_id)

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

    def list_visual_profiles(self) -> list[OpenMatbVisualProfileView]:
        with Session(self.engine) as db:
            rows = db.exec(
                select(OpenMatbVisualProfile).order_by(
                    OpenMatbVisualProfile.profile_id,
                    OpenMatbVisualProfile.created_at,
                )
            ).all()
            return [self._visual_profile_view(row) for row in rows]

    def get_visual_profile(self, profile_id: str, version: str) -> OpenMatbVisualProfileView:
        with Session(self.engine) as db:
            return self._visual_profile_view(self._visual_profile_row(db, profile_id, version))

    def clone_visual_profile(
        self,
        source_id: str,
        source_version: str,
        request: CloneVisualProfileRequest,
    ) -> OpenMatbVisualProfileView:
        with Session(self.engine) as db:
            source = self._visual_profile_row(db, source_id, source_version)
            duplicate = db.exec(
                select(OpenMatbVisualProfile).where(
                    OpenMatbVisualProfile.profile_id == request.profile_id,
                    OpenMatbVisualProfile.version == request.version,
                )
            ).first()
            if duplicate is not None:
                raise OpenMatbRuntimeError("visual_profile_already_exists")
            payload = clone_profile_identity(
                self._validated_visual_profile_payload(source),
                profile_id=request.profile_id,
                version=request.version,
                label=request.label,
            )
            assessment = assess_visual_profile(payload)
            row = OpenMatbVisualProfile(
                profile_id=payload["profile_id"],
                version=payload["version"],
                label=payload["label"],
                status="draft",
                schema_version=payload["schema_version"],
                payload_json=canonical_profile_json(payload),
                sha256=profile_sha256(payload),
                validation_json=_canonical(assessment),
                warning_acknowledgements_json="[]",
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return self._visual_profile_view(row)

    def update_visual_profile(
        self,
        profile_id: str,
        version: str,
        request: UpdateVisualProfileRequest,
    ) -> OpenMatbVisualProfileView:
        payload = validate_visual_profile(request.payload.model_dump(mode="json"))
        if payload["profile_id"] != profile_id or payload["version"] != version:
            raise OpenMatbRuntimeError("visual_profile_identity_mismatch")
        assessment = assess_visual_profile(payload)
        acknowledgements = self._validate_warning_acknowledgements(
            assessment,
            request.warning_acknowledgements,
            require_all=False,
        )
        with Session(self.engine) as db:
            row = self._visual_profile_row(db, profile_id, version)
            if row.status != "draft":
                raise OpenMatbRuntimeError("published_configuration_immutable")
            row.label = payload["label"]
            row.schema_version = payload["schema_version"]
            row.payload_json = canonical_profile_json(payload)
            row.sha256 = profile_sha256(payload)
            row.validation_json = _canonical(assessment)
            row.warning_acknowledgements_json = _canonical(acknowledgements)
            db.add(row)
            db.commit()
            db.refresh(row)
            return self._visual_profile_view(row)

    def validate_saved_visual_profile(self, profile_id: str, version: str) -> OpenMatbVisualProfileView:
        with Session(self.engine) as db:
            row = self._visual_profile_row(db, profile_id, version)
            payload = self._validated_visual_profile_payload(row)
            row.validation_json = _canonical(assess_visual_profile(payload))
            db.add(row)
            db.commit()
            db.refresh(row)
            return self._visual_profile_view(row)

    def publish_visual_profile(
        self,
        profile_id: str,
        version: str,
        request: PublishVisualProfileRequest,
    ) -> OpenMatbVisualProfileView:
        with Session(self.engine) as db:
            row = self._visual_profile_row(db, profile_id, version)
            if row.status != "draft":
                raise OpenMatbRuntimeError("published_configuration_immutable")
            payload = self._validated_visual_profile_payload(row)
            assessment = assess_visual_profile(payload)
            if assessment["errors"]:
                raise OpenMatbRuntimeError("visual_profile_accessibility_errors")
            acknowledgements = self._validate_warning_acknowledgements(
                assessment,
                request.warning_acknowledgements,
                require_all=True,
            )
            row.status = "published"
            row.validation_json = _canonical(assessment)
            row.warning_acknowledgements_json = _canonical(acknowledgements)
            row.published_at = _utcnow()
            db.add(row)
            db.commit()
            db.refresh(row)
            return self._visual_profile_view(row)

    def import_visual_profile(self, request: ImportVisualProfileRequest) -> OpenMatbVisualProfileView:
        payload = validate_visual_profile(request.payload.model_dump(mode="json"))
        sha256 = profile_sha256(payload)
        with Session(self.engine) as db:
            existing = db.exec(
                select(OpenMatbVisualProfile).where(
                    OpenMatbVisualProfile.profile_id == payload["profile_id"],
                    OpenMatbVisualProfile.version == payload["version"],
                )
            ).first()
            if existing is not None:
                if existing.sha256 != sha256:
                    raise OpenMatbRuntimeError("visual_profile_import_collision")
                return self._visual_profile_view(existing)
            assessment = assess_visual_profile(payload)
            row = OpenMatbVisualProfile(
                profile_id=payload["profile_id"],
                version=payload["version"],
                label=payload["label"],
                status="draft",
                schema_version=payload["schema_version"],
                payload_json=canonical_profile_json(payload),
                sha256=sha256,
                validation_json=_canonical(assessment),
                warning_acknowledgements_json="[]",
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return self._visual_profile_view(row)

    def export_visual_profile(self, profile_id: str, version: str) -> VisualProfileDocument:
        with Session(self.engine) as db:
            row = self._visual_profile_row(db, profile_id, version)
            return VisualProfileDocument.model_validate(self._validated_visual_profile_payload(row))

    @staticmethod
    def _validate_warning_acknowledgements(
        assessment: dict[str, list[dict[str, Any]]],
        requested: list[str],
        *,
        require_all: bool,
    ) -> list[str]:
        warning_codes = {issue["code"] for issue in assessment["warnings"]}
        acknowledgements = set(requested)
        if acknowledgements - warning_codes:
            raise OpenMatbRuntimeError("visual_profile_warning_acknowledgement_invalid")
        if require_all and warning_codes - acknowledgements:
            raise OpenMatbRuntimeError("visual_profile_warning_acknowledgement_required")
        return sorted(acknowledgements)

    @staticmethod
    def _validated_visual_profile_payload(row: OpenMatbVisualProfile) -> dict[str, Any]:
        try:
            payload = validate_visual_profile(json.loads(row.payload_json))
        except (json.JSONDecodeError, VisualProfileValidationError) as exc:
            raise OpenMatbRuntimeError("visual_profile_record_corrupt") from exc
        if (
            payload["profile_id"] != row.profile_id
            or payload["version"] != row.version
            or payload["schema_version"] != row.schema_version
            or profile_sha256(payload) != row.sha256
        ):
            raise OpenMatbRuntimeError("visual_profile_record_corrupt")
        return payload

    @classmethod
    def _visual_profile_view(cls, row: OpenMatbVisualProfile) -> OpenMatbVisualProfileView:
        payload = cls._validated_visual_profile_payload(row)
        assessment = assess_visual_profile(payload)
        try:
            acknowledgements = sorted(set(json.loads(row.warning_acknowledgements_json)))
        except (json.JSONDecodeError, TypeError) as exc:
            raise OpenMatbRuntimeError("visual_profile_record_corrupt") from exc
        warning_codes = {issue["code"] for issue in assessment["warnings"]}
        if not set(acknowledgements) <= warning_codes:
            raise OpenMatbRuntimeError("visual_profile_record_corrupt")
        unacknowledged = sorted(warning_codes - set(acknowledgements))
        validation = VisualProfileValidation(
            valid=not assessment["errors"],
            publishable=not assessment["errors"] and not unacknowledged,
            errors=assessment["errors"],
            warnings=assessment["warnings"],
            unacknowledged_warning_codes=unacknowledged,
        )
        return OpenMatbVisualProfileView(
            profile_id=row.profile_id,
            version=row.version,
            label=row.label,
            status=row.status,
            schema_version=row.schema_version,
            sha256=row.sha256,
            payload=VisualProfileDocument.model_validate(payload),
            validation=validation,
            warning_acknowledgements=acknowledgements,
            bundled=(row.profile_id, row.version) in BUNDLED_VISUAL_PROFILE_IDENTITIES,
            created_at=row.created_at,
            published_at=row.published_at,
        )

    @staticmethod
    def _visual_profile_row(db: Session, profile_id: str, version: str) -> OpenMatbVisualProfile:
        row = db.exec(
            select(OpenMatbVisualProfile).where(
                OpenMatbVisualProfile.profile_id == profile_id,
                OpenMatbVisualProfile.version == version,
            )
        ).first()
        if row is None:
            raise OpenMatbRuntimeError("visual_profile_not_found")
        return row

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

    @staticmethod
    def _legacy_theme_name(profile_id: str, version: str) -> str:
        identity = (profile_id, version)
        for name, candidate in LEGACY_THEME_PROFILE.items():
            if candidate == identity:
                return name
        return "custom"

    def _resolve_session_visual_profile(
        self,
        db: Session,
        request: CreateOpenMatbSession,
    ) -> OpenMatbVisualProfile:
        if request.visual_profile_id is not None and request.visual_profile_version is not None:
            profile_id, version = request.visual_profile_id, request.visual_profile_version
        elif request.visual_theme is not None:
            profile_id, version = LEGACY_THEME_PROFILE[request.visual_theme]
        else:
            profile_id, version = DEFAULT_VISUAL_PROFILE
        row = db.exec(
            select(OpenMatbVisualProfile).where(
                OpenMatbVisualProfile.profile_id == profile_id,
                OpenMatbVisualProfile.version == version,
                OpenMatbVisualProfile.status == "published",
            )
        ).first()
        if row is None:
            raise OpenMatbRuntimeError("published_visual_profile_not_found")
        self._validated_visual_profile_payload(row)
        return row

    @staticmethod
    def _write_visual_profile_snapshot(run_dir: Path, profile: OpenMatbVisualProfile) -> Path:
        payload = OpenMatbManager._validated_visual_profile_payload(profile)
        path = run_dir / "visual-profile.json"
        path.write_text(canonical_profile_json(payload) + "\n", encoding="utf-8", newline="\n")
        return path

    async def create_session(self, request: CreateOpenMatbSession) -> PreparedOpenMatbSession:
        async with self._lock:
            self._validate_display(request.display_index)
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
                from app.study_admission import resolve_assignment
                context = resolve_assignment(db, attempt_id=request.attempt_id, instrument='openmatb', participant_id=request.participant_id,
                    visit_id=visit.id, purpose=request.execution_purpose, require_started=True)
                if context:
                    frozen = context['config']
                    expected = (frozen['preset']['id'], frozen['preset']['version'], frozen['instructions']['id'], frozen['instructions']['version'], frozen['visual']['id'], frozen['visual']['version'])
                    actual = (request.preset_id, request.preset_version, request.instruction_protocol_id, request.instruction_version, request.visual_profile_id, request.visual_profile_version)
                    if actual != expected or request.visual_theme is not None:
                        raise OpenMatbRuntimeError('study_configuration_mismatch')
                preset = db.exec(select(OpenMatbPresetSet).where(OpenMatbPresetSet.preset_id == request.preset_id, OpenMatbPresetSet.version == request.preset_version, OpenMatbPresetSet.status == "published")).first()
                instructions = db.exec(select(OpenMatbInstructionProtocol).where(OpenMatbInstructionProtocol.protocol_id == request.instruction_protocol_id, OpenMatbInstructionProtocol.version == request.instruction_version, OpenMatbInstructionProtocol.status == "published")).first()
                if preset is None or instructions is None:
                    raise OpenMatbRuntimeError("published_configuration_not_found")
                visual_profile = self._resolve_session_visual_profile(db, request)
                visual_payload = self._validated_visual_profile_payload(visual_profile)
                session_id = str(uuid4())
                run_dir = self.artifact_root / session_id
                scenario_dir = run_dir / "scenarios"
                session_dir = run_dir / "sessions"
                scenario_dir.mkdir(parents=True, exist_ok=False)
                session_dir.mkdir(parents=True, exist_ok=False)
                self._write_visual_profile_snapshot(run_dir, visual_profile)
                settings = json.loads(preset.settings_json)
                order = ["PRACTICE"] if request.execution_purpose == "practice" else ["PRACTICE", *(level.value.upper() for level in block_order_for_participant(request.participant_id))]
                if context:
                    from app.study_bindings import binding_issues
                    from app.study_registry_schemas import OccasionSpec
                    if binding_issues(db, OccasionSpec.model_validate({key: context[key] for key in OccasionSpec.model_fields})):
                        raise OpenMatbRuntimeError('study_configuration_mismatch')
                    order = [context['condition_by_arm'][context['arm']]]
                english = instructions.locale == "en"
                isa_file = ISA_QUESTIONNAIRE if english else ISA_QUESTIONNAIRE_ES
                tlx_file = NASATLX_QUESTIONNAIRE if english else NASATLX_QUESTIONNAIRE_ES
                bedford_file = BEDFORD_QUESTIONNAIRE if english else BEDFORD_QUESTIONNAIRE_ES
                source_commit, source_dirty = detect_generator_source_provenance(self.repo_root)
                paths: dict[str, str] = {}
                for index, block in enumerate(order):
                    level = WorkloadLevel.LOW if block == "PRACTICE" else WorkloadLevel(block.lower())
                    profile = settings[block]
                    text = build_block_scenario(
                        level=level, block_duration_sec=int(profile["duration_seconds"]), seed=42 + request.visit_ordinal * 10 + index,
                        isa_questionnaire=isa_file, include_nasatlx=False, include_bedford=False,
                        workload_settings=profile,
                    )
                    path = scenario_dir / f"{index}_{block}.txt"
                    _write_scenario_with_manifest(
                        path, text, level=level, block_duration_sec=int(profile["duration_seconds"]),
                        seed=42 + request.visit_ordinal * 10 + index, isa_questionnaire=isa_file,
                        nasatlx_questionnaire=tlx_file, bedford_questionnaire=bedford_file,
                        include_nasatlx=False, include_bedford=False, participant_id=request.participant_id,
                        block_num=index + 1, visit_ordinal=request.visit_ordinal, source_commit=source_commit,
                        source_dirty=source_dirty, workload_settings=profile, profile_name=block,
                        visual_theme=self._legacy_theme_name(visual_profile.profile_id, visual_profile.version),
                        visual_profile_id=visual_profile.profile_id,
                        visual_profile_version=visual_profile.version,
                        visual_profile_schema_version=visual_profile.schema_version,
                        visual_profile_sha256=visual_profile.sha256,
                    )
                    paths[context['occasion_id'] if context else block] = str(path)
                controller_lease = secrets.token_urlsafe(32)
                participant_token = secrets.token_urlsafe(32)
                row = OpenMatbSuiteSession(
                    id=session_id, participant_id=request.participant_id, visit_id=visit.id, visit_ordinal=request.visit_ordinal,
                    preset_id=preset.preset_id, preset_version=preset.version, preset_sha256=preset.sha256,
                    instruction_protocol_id=instructions.protocol_id, instruction_version=instructions.version,
                    instruction_sha256=instructions.sha256,
                    visual_theme=self._legacy_theme_name(visual_profile.profile_id, visual_profile.version),
                    visual_profile_id=visual_profile.profile_id,
                    visual_profile_version=visual_profile.version,
                    visual_profile_schema_version=visual_profile.schema_version,
                    visual_profile_sha256=profile_sha256(visual_payload),
                    execution_purpose=request.execution_purpose, locale=instructions.locale,
                    display_index=request.display_index,
                    block_order_json=_canonical(order), scenario_paths_json=_canonical(paths),
                    controller_lease_hash=_token_hash(controller_lease), participant_token_hash=_token_hash(participant_token),
                    artifact_root=str(run_dir),
                )
                declare_acquisition(db, row, purpose=request.execution_purpose, attempt_id=request.attempt_id)
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
        from app.study_native import native_context
        context = None
        try: context = native_context(db, row)
        except HTTPException: pass
        if context:
            from app.study_registry import get_version
            from app.study_protocol import VisitDefinition
            study = json.loads(get_version(db, context['version_id']).study_json)
            protocol_visit = VisitDefinition(**next(v for v in study['visits'] if v['ordinal'] == row.visit_ordinal))
        else:
            protocol_visit = next(item for item in selected_protocol().visits if item.ordinal == row.visit_ordinal)
        instruction_view = self._instruction_view(instruction)
        order = json.loads(row.block_order_json)
        active = order[row.current_block_index] if row.current_block_index < len(order) and row.lifecycle in {"STARTING", "RUNNING", "PAUSED", "AWAITING_SCALE"} else None
        return OpenMatbSessionView(
            execution_purpose=row.execution_purpose, purpose_provenance_id=row.purpose_provenance_id, locale=row.locale,
            id=row.id, participant_id=row.participant_id, visit_ordinal=row.visit_ordinal,
            visit_code=protocol_visit.code, scheduled_day=visit.scheduled_day if visit else protocol_visit.scheduled_day,
            lifecycle=row.lifecycle, block_order=order, current_block_index=row.current_block_index, active_block=active,
            active_block_instance_id=row.active_block_instance_id if active else None,
            evidence_processing=self._processing_evidence,
            native_recovery_required=self._native_recovery_required(),
            preset_id=row.preset_id, preset_version=row.preset_version, preset_sha256=row.preset_sha256,
            instruction_protocol=instruction_view,
            visit_instruction=instruction_view.visit_instructions.get(protocol_visit.code, instruction_view.visit_instructions["DEFAULT"]),
            visual_theme=row.visual_theme,
            visual_profile_id=row.visual_profile_id,
            visual_profile_version=row.visual_profile_version,
            visual_profile_schema_version=row.visual_profile_schema_version,
            visual_profile_sha256=row.visual_profile_sha256,
            display_index=row.display_index,
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

    def _verified_session_visual_profile_path(self, row: OpenMatbSuiteSession) -> Path | None:
        """Verify the frozen profile immediately before each native launch."""

        if row.visual_profile_id is None:
            return None
        if not all(
            (
                row.visual_profile_version,
                row.visual_profile_schema_version,
                row.visual_profile_sha256,
            )
        ):
            raise OpenMatbRuntimeError("openmatb_visual_profile_provenance_incomplete")
        controlled_root = self.artifact_root.resolve()
        run_root = Path(row.artifact_root).resolve()
        if run_root.parent != controlled_root or run_root.name != row.id:
            raise OpenMatbRuntimeError("openmatb_visual_profile_path_invalid")
        profile_path = (run_root / "visual-profile.json").resolve()
        if profile_path.parent != run_root or not profile_path.is_file():
            raise OpenMatbRuntimeError("openmatb_visual_profile_path_invalid")
        try:
            payload = load_visual_profile(profile_path)
        except VisualProfileValidationError as exc:
            raise OpenMatbRuntimeError("openmatb_visual_profile_tampered") from exc
        if (
            payload["profile_id"] != row.visual_profile_id
            or payload["version"] != row.visual_profile_version
            or payload["schema_version"] != row.visual_profile_schema_version
            or profile_sha256(payload) != row.visual_profile_sha256
        ):
            raise OpenMatbRuntimeError("openmatb_visual_profile_tampered")
        return profile_path

    async def start_block(self, session_id: str, lease: str) -> OpenMatbSessionView:
        async with self._lock:
            if self._native_recovery_required():
                raise OpenMatbRuntimeError("openmatb_native_recovery_required")
            if self._processing_evidence:
                raise OpenMatbRuntimeError("openmatb_evidence_processing_active")
            if self._preview.handle is not None:
                raise OpenMatbRuntimeError("openmatb_visual_preview_active")
            with Session(self.engine) as db:
                row = self._controller_row(db, session_id, lease)
                if row.lifecycle not in {"READY", "BETWEEN_BLOCKS"}:
                    raise OpenMatbRuntimeError("openmatb_invalid_transition")
                if not self.readiness().ready:
                    raise OpenMatbRuntimeError("openmatb_station_not_ready")
                self._validate_display(row.display_index)
                from app.study_native import native_context, storage_key
                assigned_context = native_context(db, row)
                if row.execution_purpose == "study":
                    from app.experiment_catalog import require_task_order
                    try:
                        selected_source = selected_task_source(db, row)
                        if selected_source:
                            require_task_order(db, row.participant_id, row.visit_id, "openmatb", source_session_id=selected_source)
                    except ValueError as exc:
                        raise OpenMatbRuntimeError(str(exc)) from exc
                order = json.loads(row.block_order_json)
                if row.current_block_index >= len(order):
                    raise OpenMatbRuntimeError("openmatb_suite_complete")
                block = order[row.current_block_index]
                instance_key = storage_key(db, row, block)
                scenario = Path(json.loads(row.scenario_paths_json)[instance_key]).resolve()
                if scenario.parent != Path(row.artifact_root).resolve() / "scenarios" or not scenario.is_file():
                    raise OpenMatbRuntimeError("openmatb_scenario_missing")
                visual_profile_path = self._verified_session_visual_profile_path(row)
                attempt = self.records.begin(db, row, block)
                db.commit()
                command = [
                    str(self.python_executable), str(self.openmatb_root / "main.py"), "--scenario", str(scenario),
                    "--session-dir", str(Path(row.artifact_root) / "sessions" / instance_key), "--language", "en_EN" if row.locale == "en" else "es_CO",
                ]
                if visual_profile_path is None:
                    command.extend(("--visual-theme", row.visual_theme))
                else:
                    command.extend(("--theme-file", str(visual_profile_path)))
                command.extend(("--display-index", str(row.display_index), "--control-stdio"))
                session_path = Path(row.artifact_root) / "sessions" / instance_key
                session_path.mkdir(parents=True, exist_ok=True)
                kwargs: dict[str, Any] = {"cwd": str(self.openmatb_root), "stdin": asyncio.subprocess.PIPE, "stdout": asyncio.subprocess.PIPE, "stderr": asyncio.subprocess.PIPE}
                visit = db.get(Visit, row.visit_id) if row.visit_id is not None else None
                kwargs["env"] = {**os.environ, "MATB_EVIDENCE_IDENTITY": json.dumps({
                    "parent_session_id": row.id,
                    "block_instance_id": attempt.id,
                    "participant_id": row.participant_id,
                    "visit_ordinal": visit.visit_ordinal if visit is not None else None,
                    "condition": block,
                    "execution_purpose": "practice" if block == "PRACTICE" else row.execution_purpose,
                })}
                if os.name == "nt":
                    kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                else:
                    kwargs["start_new_session"] = True
                try:
                    process = await asyncio.create_subprocess_exec(*command, **kwargs)
                except OSError as exc:
                    row.lifecycle = "FAILED"; row.active_pid = None; row.last_error = "openmatb_launch_failed"
                    row.finished_at = _utcnow()
                    self.records.finish(db, row, outcome="failed", csv=None)
                    db.add(row); db.commit()
                    self.schedule_evidence_processing()
                    raise OpenMatbRuntimeError("openmatb_launch_failed") from exc
                try:
                    windows_job = _WindowsJob(process.pid) if os.name == "nt" else None
                except OSError as exc:
                    process.terminate()
                    await process.wait()
                    row.lifecycle = "FAILED"; row.active_pid = None; row.last_error = "openmatb_job_assignment_failed"
                    row.finished_at = _utcnow()
                    self.records.finish(db, row, outcome="failed", csv=None)
                    db.add(row); db.commit()
                    self.schedule_evidence_processing()
                    raise OpenMatbRuntimeError("openmatb_job_assignment_failed") from exc
                handle = _ProcessHandle(session_id=session_id, block=block, process=process, windows_job=windows_job, block_instance_id=attempt.id)
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
                # A short block can finish between ready and this refresh.
                if row.lifecycle == "STARTING":
                    row.lifecycle = "RUNNING"
                    attempt = db.get(OpenMatbBlockAttempt, row.active_block_instance_id)
                    if attempt:
                        attempt.task_status = "running"
                        attempt.session_csv = str(handle.session_csv) if handle.session_csv else None
                        db.add(attempt)
                    db.add(row); db.commit(); db.refresh(row)
                return self._view(db, row)

    def visual_profile_preview_status(self) -> VisualProfilePreviewView:
        return self._preview_view()

    async def start_visual_profile_preview(
        self,
        profile_id: str,
        version: str,
        request: VisualProfilePreviewRequest,
    ) -> VisualProfilePreviewView:
        """Launch an isolated synthetic preview that cannot enter study data."""

        async with self._lock:
            if self._native_recovery_required():
                raise OpenMatbRuntimeError("openmatb_native_recovery_required")
            if self._processing_evidence:
                raise OpenMatbRuntimeError("openmatb_evidence_processing_active")
            if self._preview.handle is not None:
                raise OpenMatbRuntimeError("openmatb_visual_preview_active")
            if self._handles:
                raise OpenMatbRuntimeError("openmatb_controlled_process_active")
            with Session(self.engine) as db:
                profile = self._visual_profile_row(db, profile_id, version)
                payload = self._validated_visual_profile_payload(profile)
            preview_id = str(uuid4())
            preview_root = (self.preview_root / preview_id).resolve()
            if preview_root.parent != self.preview_root.resolve():
                raise OpenMatbRuntimeError("openmatb_visual_preview_path_invalid")
            preview_root.mkdir(parents=True, exist_ok=False)
            session_path = preview_root / "sessions"
            session_path.mkdir(parents=False, exist_ok=False)
            profile_path = preview_root / "visual-profile.json"
            profile_path.write_text(
                canonical_profile_json(payload) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            scenario_source = self.openmatb_root / "includes" / "scenarios" / "fac_visual_preview.txt"
            scenario_path = preview_root / "fac_visual_preview.txt"
            scenario_path.write_text(
                scenario_source.read_text(encoding="utf-8"),
                encoding="utf-8",
                newline="\n",
            )
            command = [
                str(self.python_executable),
                str(self.openmatb_root / "main.py"),
                "--scenario",
                str(scenario_path),
                "--session-dir",
                str(session_path),
                "--language",
                "es_CO",
                "--theme-file",
                str(profile_path),
                "--display-index",
                str(request.display_index),
                "--control-stdio",
            ]
            if request.windowed:
                command.append("--windowed")
            kwargs: dict[str, Any] = {
                "cwd": str(self.openmatb_root),
                "stdin": asyncio.subprocess.PIPE,
                "stdout": asyncio.subprocess.PIPE,
                "stderr": asyncio.subprocess.PIPE,
            }
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                kwargs["start_new_session"] = True
            try:
                process = await asyncio.create_subprocess_exec(*command, **kwargs)
            except OSError as exc:
                self._preview = _PreviewState(
                    lifecycle="FAILED",
                    profile_id=profile_id,
                    profile_version=version,
                    profile_sha256=profile_sha256(payload),
                    artifact_root=preview_root,
                    last_error="openmatb_launch_failed",
                )
                raise OpenMatbRuntimeError("openmatb_launch_failed") from exc
            try:
                windows_job = _WindowsJob(process.pid) if os.name == "nt" else None
            except OSError as exc:
                process.terminate()
                await process.wait()
                self._preview = _PreviewState(
                    lifecycle="FAILED",
                    profile_id=profile_id,
                    profile_version=version,
                    profile_sha256=profile_sha256(payload),
                    artifact_root=preview_root,
                    last_error="openmatb_job_assignment_failed",
                )
                raise OpenMatbRuntimeError("openmatb_job_assignment_failed") from exc
            handle = _ProcessHandle(
                session_id=f"preview-{preview_id}",
                block="PREVIEW",
                process=process,
                windows_job=windows_job,
            )
            self._preview = _PreviewState(
                lifecycle="STARTING",
                profile_id=profile_id,
                profile_version=version,
                profile_sha256=profile_sha256(payload),
                artifact_root=preview_root,
                handle=handle,
            )
            handle.monitor = asyncio.create_task(self._monitor_preview(handle))
            ready_wait = asyncio.create_task(handle.ready.wait())
            exited_wait = asyncio.create_task(handle.exited.wait())
            try:
                done, _ = await asyncio.wait(
                    {ready_wait, exited_wait},
                    timeout=20,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    await self._terminate(handle)
                    self._preview.handle = None
                    self._preview.lifecycle = "FAILED"
                    self._preview.last_error = "openmatb_ready_timeout"
                    raise OpenMatbRuntimeError("openmatb_ready_timeout")
                if handle.exited.is_set() and not handle.ready.is_set():
                    failure = self._launch_failure_code(handle)
                    self._preview.handle = None
                    self._preview.lifecycle = "FAILED"
                    self._preview.last_error = failure
                    raise OpenMatbRuntimeError(failure)
            finally:
                for waiter in (ready_wait, exited_wait):
                    if not waiter.done():
                        waiter.cancel()
                await asyncio.gather(ready_wait, exited_wait, return_exceptions=True)
            self._preview.lifecycle = "RUNNING"
            return self._preview_view()

    async def _monitor_preview(self, handle: _ProcessHandle) -> None:
        async def stdout_reader() -> None:
            assert handle.process.stdout is not None
            while line := await handle.process.stdout.readline():
                try:
                    event = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if event.get("event") == "ready":
                    handle.ready.set()

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
            if self._preview.handle is not handle:
                return
            self._preview.handle = None
            if handle.ready.is_set() and handle.process.returncode == 0:
                self._preview.lifecycle = "IDLE"
                self._preview.last_error = None
            else:
                self._preview.lifecycle = "FAILED"
                self._preview.last_error = self._launch_failure_code(handle)
        self.schedule_evidence_processing()

    async def abort_visual_profile_preview(self) -> VisualProfilePreviewView:
        async with self._lock:
            handle = self._preview.handle
            if handle is not None:
                await self._terminate(handle)
            self._preview.handle = None
            self._preview.lifecycle = "IDLE"
            self._preview.last_error = None
            self.schedule_evidence_processing()
            return self._preview_view()

    def _preview_view(self) -> VisualProfilePreviewView:
        return VisualProfilePreviewView(
            lifecycle=self._preview.lifecycle,
            profile_id=self._preview.profile_id,
            profile_version=self._preview.profile_version,
            profile_sha256=self._preview.profile_sha256,
            pid=(self._preview.handle.process.pid if self._preview.handle is not None else None),
            artifact_root=(str(self._preview.artifact_root) if self._preview.artifact_root is not None else None),
            last_error=self._preview.last_error,
        )

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
                if row is None or row.lifecycle in {"ABORTED", "FAILED", "INTERRUPTED"}:
                    self._handles.pop(handle.session_id, None)
                    self.schedule_evidence_processing()
                    return
                row.active_pid = None
                if not handle.ready.is_set() or handle.process.returncode != 0:
                    row.lifecycle = "FAILED"
                    row.finished_at = _utcnow()
                    row.last_error = self._launch_failure_code(handle)
                    self.records.finish(db, row, outcome="failed", csv=handle.session_csv)
                else:
                    row.active_session_csv = str(handle.session_csv) if handle.session_csv else None
                    self.records.finish(db, row, outcome="completed", csv=handle.session_csv)
                    if handle.block == "PRACTICE":
                        row.current_block_index += 1
                        row.lifecycle = "COMPLETE" if row.execution_purpose == "practice" else "BETWEEN_BLOCKS"
                        if row.execution_purpose == "practice":
                            row.finished_at = _utcnow()
                    else:
                        row.lifecycle = "AWAITING_SCALE"
                db.add(row); db.commit()
            self._handles.pop(handle.session_id, None)
        self.schedule_evidence_processing()

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
            row.active_block_instance_id = None
            db.add(row); db.commit(); db.refresh(row)
            return self._view(db, row)

    async def _command(self, session_id: str, lease: str, command: str, lifecycle: str, allowed: set[str]) -> OpenMatbSessionView:
        async with self._lock:
            with Session(self.engine) as db:
                row = self._controller_row(db, session_id, lease)
                if command == 'resume':
                    from app.study_admission import guard_source
                    guard_source(db, row)
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
                    self.records.finish(db, row, outcome="aborted", csv=handle.session_csv)
                from app.study_admission import sync_runtime_attempt
                sync_runtime_attempt(db, row, state='interrupted', cause='operator_stop')
                row.lifecycle = "ABORTED"; row.active_pid = None; row.last_error = reason; row.finished_at = _utcnow()
                db.add(row); db.commit(); db.refresh(row)
                self._handles.pop(session_id, None)
                self.schedule_evidence_processing()
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
        return self.submit_scale_once(session_id, participant_token, request)[0]

    def submit_scale_once(self, session_id: str, participant_token: str, request: WorkloadScaleRequest) -> tuple[OpenMatbSessionView, bool]:
        # The HTTP endpoint runs on the control loop; this also serializes
        # synchronous callers and retries from other threads in this manager.
        with self._scale_lock, Session(self.engine) as db:
            row = self._participant_row(db, session_id, participant_token)
            if row.receipt_version >= 1 and request.block_instance_id is None:
                raise OpenMatbRuntimeError("openmatb_block_identity_required")
            attempt = None
            submission = _canonical({"nasa_tlx": request.nasa_tlx, "bedford": request.bedford})
            if request.block_instance_id is not None:
                attempt = db.get(OpenMatbBlockAttempt, request.block_instance_id)
                if attempt is None or attempt.session_id != row.id:
                    raise OpenMatbRuntimeError("openmatb_block_mismatch")
                if attempt.ratings_json is not None:
                    if attempt.ratings_json != submission:
                        raise OpenMatbRuntimeError("openmatb_scale_already_saved")
                    return self._view(db, row), False
                if row.active_block_instance_id != attempt.id or row.current_block_index != attempt.block_index:
                    raise OpenMatbRuntimeError("openmatb_block_mismatch")
            if row.lifecycle != "AWAITING_SCALE":
                raise OpenMatbRuntimeError("openmatb_scale_not_expected")
            order = json.loads(row.block_order_json)
            block = order[row.current_block_index]
            scores = json.loads(row.scores_json)
            from app.study_native import native_context, storage_key, save_ratings
            native_context(db, row)
            instance_key = storage_key(db, row, block)
            scores[instance_key] = {
                "instrument_version": "MATB-FAC-WORKLOAD-1.0",
                **({"occasion_id": instance_key, "condition": block} if instance_key != block else {}),
                "locale": row.locale,
                "nasa_tlx": request.nasa_tlx,
                "rtlx_mean_0_100": sum(request.nasa_tlx.values()) / 6,
                "bedford": request.bedford,
                "bedford_status": "exploratory_translation_not_locally_validated",
                **({"block_instance_id": attempt.id} if attempt else {}),
            }
            self._persist_scale_sidecar(row, instance_key, scores[instance_key])
            legacy_status, legacy_error = "not_required", None
            if row.execution_purpose == "study":
                legacy_status, legacy_error = self._ingest_completed_block(db, row, block, request)
            # The legacy importer manages its own commit/rollback. Assign the
            # authoritative ratings afterward so an import failure cannot
            # erase them or partially advance the participant's session.
            row.scores_json = _canonical(scores)
            if attempt:
                attempt.ratings_json = submission
                attempt.ratings_saved_at = _utcnow()
                attempt.legacy_import_status = legacy_status
                attempt.legacy_import_error = legacy_error
                db.add(attempt)
                save_ratings(db, row, attempt)
            row.current_block_index += 1
            row.active_block_instance_id = None
            row.lifecycle = "COMPLETE" if row.current_block_index >= len(order) else "BETWEEN_BLOCKS"
            if row.lifecycle == "COMPLETE":
                row.finished_at = _utcnow()
                visit = db.get(Visit, row.visit_id)
                if visit is not None and row.execution_purpose == "study" and instance_key == block:
                    visit.status = "complete"; db.add(visit)
            db.add(row); db.commit(); db.refresh(row)
            if row.lifecycle == "COMPLETE":
                self.schedule_evidence_processing()
            return self._view(db, row), True

    @staticmethod
    def _persist_scale_sidecar(row: OpenMatbSuiteSession, block: str, payload: object) -> None:
        path = Path(row.artifact_root) / "scales" / f"{block}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_canonical(payload) + "\n", encoding="utf-8", newline="\n")

    def _ingest_completed_block(self, db: Session, row: OpenMatbSuiteSession, block: str, request: WorkloadScaleRequest) -> tuple[str, str | None]:
        from app.study_native import native_context
        if native_context(db, row):
            return 'inapplicable_assigned_occasion', None
        if not row.active_session_csv:
            return "missing", "session_csv_missing"
        csv_path = Path(row.active_session_csv).resolve()
        session_root = (Path(row.artifact_root) / "sessions").resolve()
        if session_root not in csv_path.parents or not csv_path.is_file():
            row.last_error = "session_csv_outside_artifact_root"
            return "failed", row.last_error
        try:
            content = csv_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return "failed", "session_csv_unreadable"
        lines = content.splitlines()
        if not lines:
            row.last_error = "session_csv_empty"
            return "missing", row.last_error
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
        from app.models import Block
        existing = db.exec(select(Block).where(Block.visit_id == row.visit_id, Block.workload_level == block)).first()
        if existing and existing.source_csv_sha256 == hashlib.sha256(merged).hexdigest():
            return "saved", None
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
            return "failed", "automatic_ingest_failed"
        return "saved", None

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
                handle = self._handles.get(session_id)
                self.records.finish(db, row, outcome="interrupted" if code == "backend_shutdown" else "failed",
                                    csv=handle.session_csv if handle else None)
                row.lifecycle = "FAILED"
                row.active_pid = None
                row.last_error = code
                row.finished_at = _utcnow()
                db.add(row)
                db.commit()
        self.schedule_evidence_processing()

    async def shutdown(self) -> None:
        self._closing = True
        async with self._lock:
            if self._preview.handle is not None:
                await self._terminate(self._preview.handle)
                self._preview.handle = None
                self._preview.lifecycle = "IDLE"
            for handle in list(self._handles.values()):
                await self._terminate(handle)
                self._set_failure(handle.session_id, "backend_shutdown")
            self._handles.clear()
        # Do not cancel a to_thread import: its DB work would outlive the gate.
        if self._evidence_task is not None:
            await self._evidence_task
