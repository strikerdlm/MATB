"""REST API for the native sUAS simulation runtime.

The router deliberately stays thin: lifecycle and command semantics belong to
``SimulationManager`` while this module owns transport validation, lease
authentication, stable HTTP errors, and public redaction.  No controller lease
or filesystem implementation detail is returned from an ordinary public view.
"""

from __future__ import annotations

import asyncio
import json
import io
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID
import zipfile

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import Response
from sqlmodel import Session, select
import yaml

from app.db import get_session
from app.models import Visit
from app.simulation_models import (
    SimulationArtifact,
    SimulationSession,
    TechnicalSimulationArtifact,
    TechnicalSimulationSession,
)
from app.simulation_runtime import (
    InvalidLease,
    InvalidTransition,
    PostBlockGateActive,
    ProtocolGateActive,
    SimulationConflict,
    SimulationError,
    SimulationManager,
    SimulationNotFound,
)
from app.websocket.simulation import HubConflict
from app.simulation_schemas import (
    ArtifactView,
    CommandRequest,
    CommandResultView,
    CreateSimulationSession,
    CreateTechnicalSimulationSession,
    ErrorDetail,
    FinishRequest,
    LifecycleRequest,
    PreparedSession,
    PresentationEvent,
    RecoverRequest,
    RecoveryView,
    ScenarioSummary,
    ScenarioProfileSummary,
    ScenarioValidationView,
    SessionView,
)

from matb_integration.suas.recording.records import RecordingError
from matb_integration.suas.recording.artifacts import verify_checksum_file
from matb_integration.suas.research.protocol import ProtocolError
from matb_integration.suas.scenarios.loader import MAX_YAML_BYTES, load_scenario, load_scenario_text


router = APIRouter(prefix="/simulation", tags=["simulation"])

_T = TypeVar("_T")
_LEASE_HEADER = "X-Simulation-Controller"
_PUBLIC_SECRET_KEYS = frozenset({
    "controller_lease", "lease", "lease_hash", "truth", "truth_priority",
    "required_report", "correct_answer", "answer", "private_probe", "evaluator",
    "future_schedule", "artifact_root", "run_dir", "absolute_path",
})


async def get_simulation_manager(request: Request) -> SimulationManager:
    """Resolve the process-local runtime or fail closed when unavailable."""

    manager = getattr(request.app.state, "simulation_manager", None)
    if manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ErrorDetail(
                code="simulation_unavailable",
                message="simulation runtime is unavailable",
            ).model_dump(exclude_none=True),
        )
    return manager


def _error(
    status_code: int,
    code: str,
    message: str,
    *,
    context: Mapping[str, Any] | None = None,
) -> HTTPException:
    detail = ErrorDetail(
        code=code,
        message=message,
        context=dict(context) if context is not None else None,
    )
    return HTTPException(status_code=status_code, detail=detail.model_dump(exclude_none=True))


def _stable_code(exc: BaseException) -> str:
    """Map manager messages to the more useful stable public error code."""

    if isinstance(exc, InvalidLease):
        return "invalid_lease"
    if isinstance(exc, SimulationConflict):
        return "active_session"
    if isinstance(exc, InvalidTransition):
        return "invalid_transition"
    if isinstance(exc, ProtocolGateActive):
        return "probe_active"
    if isinstance(exc, PostBlockGateActive):
        return "post_block_active"
    if isinstance(exc, ProtocolError):
        return exc.code
    if isinstance(exc, SimulationNotFound):
        message = str(exc).lower()
        if "participant" in message:
            return "participant_not_found"
        if "visit" in message:
            return "visit_not_found"
        if "scenario" in message:
            return "scenario_not_found"
        return "simulation_not_found"
    if isinstance(exc, RecordingError):
        return "recording_error"
    if isinstance(exc, SimulationError):
        return getattr(exc, "code", "simulation_error")
    if isinstance(exc, UnicodeDecodeError):
        return "scenario_not_utf8"
    if isinstance(exc, (ValueError, yaml.YAMLError)):
        return "invalid_request"
    return "simulation_error"


def _translate(exc: BaseException) -> HTTPException:
    code = _stable_code(exc)
    if isinstance(exc, (InvalidLease,)):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, (SimulationNotFound,)):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, (SimulationConflict, InvalidTransition, ProtocolGateActive, PostBlockGateActive)):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(exc, RecordingError):
        status_code = status.HTTP_507_INSUFFICIENT_STORAGE
    elif isinstance(exc, (ValueError, UnicodeDecodeError, yaml.YAMLError)):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    message = str(exc) or code.replace("_", " ")
    return _error(status_code, code, message)


async def _managed(awaitable: Awaitable[_T]) -> _T:
    try:
        return await awaitable
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - translated at the HTTP boundary
        raise _translate(exc) from exc


def _lease_or_error(value: str | None) -> str:
    # FastAPI's Header default is optional so that a missing lease is a stable
    # 403 rather than a generic 422 request-shape error.
    if value is None or not value.strip():
        raise _error(status.HTTP_403_FORBIDDEN, "invalid_lease", "controller lease is required")
    return value


def _scenario_summary(loaded: Any) -> ScenarioSummary:
    definition = loaded.definition
    title = definition.title.get("en") or next(iter(definition.title.values()), None)
    description = definition.description.get("en") or next(iter(definition.description.values()), None)
    locales = sorted({getattr(locale, "value", str(locale)) for locale in definition.title})
    # ``ScenarioDefinition.blocks`` is normalized by ID.  The protocol's
    # PRACTICE-first order is stable for scenario listing even though each
    # participant receives a counterbalanced LOW/MEDIUM/HIGH order at prepare.
    block_order = [block_id for block_id in ("PRACTICE", "LOW", "MEDIUM", "HIGH") if block_id in definition.blocks]
    profile_details = {
        block_id: ScenarioProfileSummary(
            duration_seconds=max(1, definition.blocks[block_id].duration_ms // 1_000),
            aircraft_count=len(definition.blocks[block_id].aircraft_ids),
            contact_count=len(definition.blocks[block_id].contact_ids),
            calibration_status="engineering_preset_pending_human_calibration",
        )
        for block_id in block_order
    }
    return ScenarioSummary(
        scenario_id=definition.scenario_id,
        scenario_sha256=loaded.sha256,
        title=title,
        description=description,
        titles={getattr(key, "value", str(key)): value for key, value in definition.title.items()},
        descriptions={getattr(key, "value", str(key)): value for key, value in definition.description.items()},
        aircraft_count=len(definition.aircraft),
        block_order=block_order,
        locales=locales,
        profile_details=profile_details,
    )


def _direct_yaml_files(root: Path) -> list[Path]:
    """Resolve only direct YAML children of a configured scenario directory."""

    try:
        root_resolved = root.resolve()
        if not root_resolved.is_dir():
            return []
        return sorted(
            path for path in root_resolved.iterdir()
            if path.is_file()
            and path.suffix.lower() == ".yaml"
            and path.resolve().is_file()
            and path.resolve().parent == root_resolved
        )
    except OSError:
        return []


@router.get("/scenarios", response_model=list[ScenarioSummary])
async def list_scenarios(manager: SimulationManager = Depends(get_simulation_manager)) -> list[ScenarioSummary]:
    summaries: list[ScenarioSummary] = []
    for path in _direct_yaml_files(manager.scenario_root):
        try:
            summaries.append(_scenario_summary(load_scenario(path)))
        except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError):
            # The listing is intentionally limited to installed *valid*
            # scenarios.  Invalid files remain visible to an operator through
            # the explicit upload validation endpoint, never as executable
            # entries in the setup screen.
            continue
    return summaries


@router.post("/scenarios/validate", response_model=ScenarioValidationView)
async def validate_scenario(request: Request) -> ScenarioValidationView:
    """Validate one bounded UTF-8 YAML upload without installing it."""

    # Read at most one byte beyond the configured limit so a hostile upload
    # cannot force an unbounded allocation before validation rejects it.
    try:
        form = await request.form()
    except Exception as exc:  # noqa: BLE001
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "scenario_read_error", "scenario upload could not be read") from exc
    uploads = [
        value for _, value in form.multi_items()
        if hasattr(value, "filename") and hasattr(value, "read")
    ]
    if len(uploads) != 1:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "scenario_file_required", "exactly one scenario file is required")
    file = uploads[0]
    try:
        payload = await file.read(MAX_YAML_BYTES + 1)
    except Exception as exc:  # noqa: BLE001
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "scenario_read_error", "scenario upload could not be read") from exc
    if len(payload) > MAX_YAML_BYTES:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "scenario_too_large",
            f"scenario exceeds {MAX_YAML_BYTES} UTF-8 bytes",
        )
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "scenario_not_utf8", "scenario must be UTF-8") from exc
    try:
        loaded = load_scenario_text(text, source_name=file.filename or "<upload>")
    except (TypeError, ValueError, yaml.YAMLError) as exc:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "scenario_invalid", str(exc)) from exc
    summary = _scenario_summary(loaded)
    return ScenarioValidationView(
        valid=True,
        scenario_id=loaded.definition.scenario_id,
        scenario_sha256=loaded.sha256,
        summary=summary,
    )


@router.post("/sessions", response_model=PreparedSession, status_code=status.HTTP_201_CREATED)
async def prepare_session(
    body: CreateSimulationSession,
    manager: SimulationManager = Depends(get_simulation_manager),
    db: Session = Depends(get_session),
) -> PreparedSession:
    return await _managed(manager.prepare(body, db))


@router.post(
    "/technical-sessions",
    response_model=PreparedSession,
    status_code=status.HTTP_201_CREATED,
)
async def prepare_technical_session(
    body: CreateTechnicalSimulationSession,
    manager: SimulationManager = Depends(get_simulation_manager),
    db: Session = Depends(get_session),
) -> PreparedSession:
    """Prepare a direct one-block launch that is never participant data."""

    return await _managed(manager.prepare_technical(body, db))


SessionMetadataRow = SimulationSession | TechnicalSimulationSession


def _session_row(db: Session, session_id: str) -> SessionMetadataRow | None:
    row = db.get(SimulationSession, session_id)
    if row is not None:
        return row
    return db.get(TechnicalSimulationSession, session_id)


def _session_view_from_row(row: SessionMetadataRow, db: Session) -> SessionView:
    """Rehydrate public metadata for a sealed session after a process restart."""

    try:
        manifest = json.loads(row.manifest_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        manifest = {}
    technical = isinstance(row, TechnicalSimulationSession)
    selected_block_id = row.selected_block_id if technical else None
    block_order = (
        [selected_block_id]
        if selected_block_id is not None
        else manifest.get("block_order", []) if isinstance(manifest, Mapping) else []
    )
    if not isinstance(block_order, list) or not all(isinstance(item, str) for item in block_order):
        block_order = []
    visit_id = getattr(row, "visit_id", None)
    participant_id = getattr(row, "participant_id", None)
    visit = db.get(Visit, visit_id) if visit_id is not None else None
    return SessionView(
        id=row.id,
        presentation=manifest.get("presentation"),
        console_profile=manifest.get("console_profile"),
        participant_id=participant_id,
        visit_id=visit_id,
        visit_ordinal=visit.visit_ordinal if visit is not None else None,
        scenario_id=row.scenario_id,
        scenario_sha256=row.scenario_sha256,
        locale=row.locale,
        lifecycle=row.lifecycle,
        active_block_id=row.active_block_id,
        validity=row.validity,
        execution_purpose="practice" if technical else "study",
        session_mode="interactive_technical" if technical else "research",
        record_class="technical_only" if technical else "research",
        selected_block_id=selected_block_id,
        block_order=block_order,
        state_version=0,
        simulation_time_ms=0,
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
        interrupted_at=row.interrupted_at,
    )


@router.get("/sessions/{session_id}", response_model=SessionView)
async def get_session_view(
    session_id: str,
    manager: SimulationManager = Depends(get_simulation_manager),
    db: Session = Depends(get_session),
) -> SessionView:
    try:
        return await manager.view(session_id)
    except SimulationNotFound:
        row = _session_row(db, session_id)
        if row is None:
            raise _error(status.HTTP_404_NOT_FOUND, "simulation_not_found", "simulation not found")
        return _session_view_from_row(row, db)


@router.post("/sessions/{session_id}/start", response_model=SessionView)
async def start_session(
    session_id: str,
    body: LifecycleRequest,
    lease: str | None = Header(default=None, alias=_LEASE_HEADER),
    manager: SimulationManager = Depends(get_simulation_manager),
) -> SessionView:
    controller_lease = _lease_or_error(lease)
    if body.block_id is None:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "block_required", "block_id is required to start a block")
    return await _managed(manager.start(session_id, body.block_id, controller_lease))


@router.post("/sessions/{session_id}/pause", response_model=SessionView)
async def pause_session(
    session_id: str,
    body: LifecycleRequest,
    lease: str | None = Header(default=None, alias=_LEASE_HEADER),
    manager: SimulationManager = Depends(get_simulation_manager),
) -> SessionView:
    controller_lease = _lease_or_error(lease)
    return await _managed(manager.pause(session_id, controller_lease, body.reason or "operator_pause"))


@router.post("/sessions/{session_id}/resume", response_model=SessionView)
async def resume_session(
    session_id: str,
    body: LifecycleRequest,
    lease: str | None = Header(default=None, alias=_LEASE_HEADER),
    manager: SimulationManager = Depends(get_simulation_manager),
) -> SessionView:
    del body  # the strict empty-object-compatible request is intentionally unused
    controller_lease = _lease_or_error(lease)
    return await _managed(manager.resume(session_id, controller_lease))


@router.post("/sessions/{session_id}/recover", response_model=RecoveryView)
async def recover_session(
    session_id: str,
    body: RecoverRequest,
    lease: str | None = Header(default=None, alias=_LEASE_HEADER),
    manager: SimulationManager = Depends(get_simulation_manager),
) -> RecoveryView:
    active = manager.active
    if active is not None:
        controller_lease = _lease_or_error(lease)
    else:
        # A process-restart recovery has no in-memory handle and therefore no
        # lease to authenticate.  Explicit confirmation is mandatory.
        controller_lease = lease
        if controller_lease is None and not body.confirm_process_restart:
            raise _error(
                status.HTTP_403_FORBIDDEN,
                "invalid_lease",
                "process-restart recovery requires confirmation",
            )
    recover = getattr(manager, "recover", None)
    if recover is None:
        raise _error(
            status.HTTP_409_CONFLICT,
            "recovery_unavailable",
            "simulation recovery is not available",
        )
    return await _managed(
        recover(
            session_id,
            controller_lease,
            checkpoint_version=body.checkpoint_version,
            confirm_process_restart=body.confirm_process_restart,
        )
    )


@router.post("/sessions/{session_id}/finish", response_model=SessionView)
async def finish_session(
    session_id: str,
    body: FinishRequest,
    lease: str | None = Header(default=None, alias=_LEASE_HEADER),
    manager: SimulationManager = Depends(get_simulation_manager),
) -> SessionView:
    controller_lease = _lease_or_error(lease)
    return await _managed(manager.finish(session_id, controller_lease, body))


@router.post("/sessions/{session_id}/commands", response_model=CommandResultView)
async def submit_command(
    session_id: str,
    body: CommandRequest,
    lease: str | None = Header(default=None, alias=_LEASE_HEADER),
    manager: SimulationManager = Depends(get_simulation_manager),
) -> CommandResultView:
    controller_lease = _lease_or_error(lease)
    result = await _managed(manager.submit(session_id, controller_lease, body))
    try:
        status_value = result.status.value
        command_id = UUID(str(result.command_id))
    except (AttributeError, TypeError, ValueError) as exc:
        raise _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "invalid_command_result", "runtime returned an invalid command result") from exc
    # The result carries the reducer's authoritative state version.  Reading
    # the public snapshot supplies the matching simulation time without making
    # a second mutation or exposing private engine state.
    try:
        snapshot = await manager.state(session_id)
    except Exception as exc:  # noqa: BLE001
        raise _translate(exc) from exc
    return CommandResultView(
        command_id=command_id,
        status=status_value,
        code=result.code,
        expected_state_version=body.expected_state_version,
        state_version=max(0, int(result.state_version)),
        simulation_time_ms=max(0, int(snapshot.get("simulation_time_ms", 0))),
        payload={},
    )


@router.get("/sessions/{session_id}/state")
async def get_state(
    session_id: str,
    manager: SimulationManager = Depends(get_simulation_manager),
) -> dict[str, object]:
    state = await _managed(manager.state(session_id))
    return _sanitize_public(state)


async def _terminal_session(
    session_id: str,
    manager: SimulationManager,
    db: Session,
) -> SessionView:
    try:
        view = await manager.view(session_id)
    except SimulationNotFound:
        row = _session_row(db, session_id)
        if row is None:
            raise _error(status.HTTP_404_NOT_FOUND, "simulation_not_found", "simulation not found")
        view = _session_view_from_row(row, db)
    if view.lifecycle not in {"FINISHED", "ABORTED"}:
        raise _error(
            status.HTTP_409_CONFLICT,
            "simulation_not_finished",
            "artifacts and debrief are available only after the session finishes",
        )
    return view


def _safe_relative(path: Path, *, root: Path | None = None) -> str | None:
    try:
        if path.is_absolute():
            if root is None:
                return None
            relative = path.resolve().relative_to(root.resolve())
        else:
            relative = path
        text = relative.as_posix()
        if not text or text.startswith("/") or text == "." or ".." in Path(text).parts:
            return None
        return text
    except (OSError, ValueError):
        return None


def _artifact_views(
    session_id: str,
    manager: SimulationManager,
    db: Session,
) -> list[ArtifactView]:
    technical = db.get(TechnicalSimulationSession, session_id) is not None
    artifact_model = TechnicalSimulationArtifact if technical else SimulationArtifact
    rows = db.exec(
        select(artifact_model)
        .where(artifact_model.session_id == session_id)
        .order_by(artifact_model.relative_path)
    ).all()
    if rows:
        views: list[ArtifactView] = []
        for row in rows:
            relative = _safe_relative(Path(row.relative_path))
            if relative is None:
                continue
            views.append(ArtifactView(
                kind=row.kind,
                relative_path=relative,
                sha256=row.sha256,
                size_bytes=row.size_bytes,
                created_at=row.created_at,
            ))
        return views
    # Endpoint tests use the in-memory adapter.  Keep the same public shape
    # without leaking the adapter's absolute temporary artifact root.
    inventory = getattr(manager.persistence, "artifacts", {}).get(session_id, ())
    root: Path | None = None
    active = manager.active
    if active is not None and active.session_id == session_id:
        root = active.recorder.run_dir
    views: list[ArtifactView] = []
    for artifact in inventory:
        relative = _safe_relative(artifact.path, root=root)
        if relative is None:
            continue
        views.append(ArtifactView(
            kind=artifact.kind,
            relative_path=relative,
            sha256=artifact.sha256,
            size_bytes=artifact.size_bytes,
        ))
    return sorted(views, key=lambda value: value.relative_path)


@router.get("/sessions/{session_id}/artifacts", response_model=list[ArtifactView])
async def get_artifacts(
    session_id: str,
    manager: SimulationManager = Depends(get_simulation_manager),
    db: Session = Depends(get_session),
) -> list[ArtifactView]:
    await _terminal_session(session_id, manager, db)
    return _artifact_views(session_id, manager, db)


def _session_run_dir(session_id: str, manager: SimulationManager, db: Session) -> Path | None:
    active = manager.active
    if active is not None and active.session_id == session_id:
        return active.recorder.run_dir
    row = _session_row(db, session_id)
    if row is None:
        return None
    # The path is trusted only as an internal server-side lookup.  It is never
    # returned to the browser and is constrained to the configured artifact
    # root where possible.
    configured_root = (
        (manager.artifact_root / "technical").resolve()
        if isinstance(row, TechnicalSimulationSession)
        else manager.artifact_root.resolve()
    )
    path = Path(row.artifact_root)
    if not path.is_absolute():
        path = configured_root / path
    try:
        resolved = path.resolve()
        if resolved.parent != configured_root or resolved.name != session_id:
            return None
        return resolved
    except OSError:
        return None


@router.get("/sessions/{session_id}/debrief")
async def get_debrief(
    session_id: str,
    manager: SimulationManager = Depends(get_simulation_manager),
    db: Session = Depends(get_session),
) -> dict[str, object]:
    view = await _terminal_session(session_id, manager, db)
    run_dir = _session_run_dir(session_id, manager, db)
    if run_dir is None:
        raise _error(status.HTTP_404_NOT_FOUND, "debrief_not_found", "debrief artifact not found")
    path = run_dir / "debrief.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        # Aborted runs are intentionally partial and have no debrief artifact;
        # expose a stable, explicitly incomplete public view instead.
        if view.lifecycle == "ABORTED":
            return {
                "status": "partial_unverified",
                **({"console_profile": view.console_profile.model_dump(mode="json")} if view.console_profile is not None else {}),
                "timeline": [],
                "session_mode": view.session_mode,
                "record_class": view.record_class,
                "selected_block_id": view.selected_block_id,
            }
        raise _error(status.HTTP_404_NOT_FOUND, "debrief_not_found", "debrief artifact not found") from exc
    if not isinstance(payload, dict):
        raise _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "invalid_debrief", "debrief artifact is not a JSON object")
    return _sanitize_public(payload)


@router.get("/sessions/{session_id}/bundle")
async def get_public_bundle(
    session_id: str,
    manager: SimulationManager = Depends(get_simulation_manager),
    db: Session = Depends(get_session),
) -> Response:
    """Download a checksum-verified public bundle without private run files."""

    view = await _terminal_session(session_id, manager, db)
    run_dir = _session_run_dir(session_id, manager, db)
    if run_dir is None:
        raise _error(status.HTTP_404_NOT_FOUND, "bundle_not_found", "public bundle not found")
    checksum_path = run_dir / "checksums.sha256"
    checksum_codes = verify_checksum_file(checksum_path) if checksum_path.is_file() else ("checksum_missing",)
    if checksum_codes:
        raise _error(
            status.HTTP_409_CONFLICT,
            "artifact_integrity_failed",
            "sealed artifact checksums could not be verified",
            context={"codes": list(checksum_codes)},
        )
    allowed = (
        "debrief.json", "metrics.json", "replay-verification.json", "partial-run.json", "checksums.sha256", "presentation.jsonl", "traffic.jsonl",
    )
    manifest = {
        "bundle_version": "suas-public-bundle-v1",
        **({"console_profile": view.console_profile.model_dump(mode="json")} if view.console_profile is not None else {}),
        "session_id": session_id,
        "scenario_id": view.scenario_id,
        "scenario_sha256": view.scenario_sha256,
        "lifecycle": view.lifecycle,
        "validity": view.validity,
        "session_mode": view.session_mode,
        "record_class": view.record_class,
        "selected_block_id": view.selected_block_id,
        "private_files_excluded": ["events.jsonl", "questionnaires.json", "scenario.yaml", "checkpoints/"],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n")
        for name in allowed:
            path = run_dir / name
            if not path.is_file():
                continue
            archive.writestr(name, path.read_bytes())
    filename = f"{session_id}_suas_public_bundle.zip"
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _sanitize_public(value: Any, *, key: str | None = None) -> Any:
    """Defensive redaction for future state/debrief payload extensions."""

    if key is not None and key.lower() in _PUBLIC_SECRET_KEYS:
        return None
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for child_key, child_value in value.items():
            if str(child_key).lower() in _PUBLIC_SECRET_KEYS:
                continue
            sanitized = _sanitize_public(child_value, key=str(child_key))
            if sanitized is None and child_value is not None:
                continue
            out[str(child_key)] = sanitized
        return out
    if isinstance(value, (list, tuple)):
        return [_sanitize_public(item) for item in value]
    if isinstance(value, Path):
        return None
    if isinstance(value, str) and value.startswith(("/", "\\")):
        return None
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return value


@router.websocket("/sessions/{session_id}/stream")
async def simulation_stream(websocket: WebSocket, session_id: str) -> None:
    """Serve one ordered controller or observer stream for a session."""

    origin = websocket.headers.get("origin")
    if origin is None or origin not in websocket.app.state.frontend_origins:
        await websocket.close(code=4403)
        return
    manager = getattr(websocket.app.state, "simulation_manager", None)
    if manager is None:
        await websocket.close(code=4503)
        return
    try:
        after_sequence = int(websocket.query_params.get("after_sequence", "0"))
    except (TypeError, ValueError):
        await websocket.close(code=4400)
        return
    if after_sequence < 0:
        await websocket.close(code=4400)
        return
    lease = websocket.query_params.get("lease")
    role = "controller" if lease else "observer"
    controller_handshake_pending = False
    subscription = None
    try:
        if lease:
            await manager.controller_connected(session_id, lease)
            controller_handshake_pending = True
        else:
            await manager.view(session_id)
        subscription = await manager.hub.subscribe(
            session_id,
            role=role,
            identity=lease if role == "controller" else None,
        )
        if lease:
            await manager.controller_stream_established(session_id, lease)
            controller_handshake_pending = False
        initial = await manager.snapshot_envelope(session_id, after_sequence=after_sequence)
    except HubConflict:
        if lease and controller_handshake_pending:
            await manager.controller_stream_failed(session_id, lease)
        await websocket.close(code=4409)
        return
    except Exception:
        if lease and controller_handshake_pending:
            try:
                await manager.controller_stream_failed(session_id, lease)
            except Exception:
                pass
        if subscription is not None:
            await manager.hub.unsubscribe(subscription)
        await websocket.close(code=4403 if lease else 4404)
        return

    await websocket.accept()
    receive_task = asyncio.create_task(websocket.receive())
    queue_task = asyncio.create_task(subscription.queue.get())
    closed_task = asyncio.create_task(subscription._closed.wait())
    try:
        await websocket.send_json(initial.as_json())
        while True:
            done, _ = await asyncio.wait(
                {receive_task, queue_task, closed_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            # A disconnect and queued frame can arrive in the same loop turn.
            # Do not send that frame after the transport has already closed.
            if receive_task in done and receive_task.result().get("type") == "websocket.disconnect":
                break
            if closed_task in done:
                if websocket.client_state.value != "DISCONNECTED":
                    await websocket.close(code=subscription.closed_code or 4408)
                break
            if queue_task in done:
                envelope = queue_task.result()
                await websocket.send_json(envelope.as_json())
                queue_task = asyncio.create_task(subscription.queue.get())
            if receive_task in done:
                message = receive_task.result()
                if message.get("type") == "websocket.disconnect":
                    break
                raw = message.get("text")
                if raw is None:
                    await websocket.close(code=4400)
                    break
                try:
                    payload = json.loads(raw)
                except (TypeError, ValueError, json.JSONDecodeError):
                    await websocket.close(code=4400)
                    break
                if payload != {"kind": "ping"}:
                    await websocket.close(code=4400)
                    break
                await websocket.send_json({"kind": "pong"})
                receive_task = asyncio.create_task(websocket.receive())
    except WebSocketDisconnect:
        pass
    finally:
        for task in (receive_task, queue_task, closed_task):
            if not task.done():
                task.cancel()
        await manager.hub.unsubscribe(subscription)
        try:
            if role == "controller":
                await manager.controller_disconnected(session_id, lease or "")
            else:
                await manager.observer_disconnected(session_id)
        except Exception:
            pass


__all__ = ["get_simulation_manager", "router", "simulation_stream"]


@router.get("/scenes")
async def list_presentation_scenes():
    from matb_integration.suas.presentation.packages import catalog
    return catalog()


@router.post("/sessions/{session_id}/presentation", status_code=204)
async def record_presentation(
    session_id: str,
    event: PresentationEvent,
    manager: SimulationManager = Depends(get_simulation_manager),
    lease: str | None = Header(default=None, alias=_LEASE_HEADER),
):
    await _managed(manager.presentation_event(session_id, _lease_or_error(lease), event))
    return Response(status_code=204)
