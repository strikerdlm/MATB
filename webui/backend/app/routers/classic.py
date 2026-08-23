"""REST API for native Polar H10 + classic OpenMATB acquisition."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import importlib.metadata
import io
import platform
import zipfile

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import Response

from app.classic_runtime import ClassicManager, ClassicRuntimeError
from app.classic_exports import (
    visit_summary_csv,
    visit_summary_json,
    visit_summary_markdown,
)
from app.classic_schemas import (
    AbortClassicSession,
    ClassicArtifactView,
    ClassicDebriefView,
    ClassicScenarioView,
    ClassicSessionView,
    CreateClassicSession,
    EmptyRequest,
    PolarCapabilitiesView,
    PolarConnectRequest,
    PolarDeviceView,
    PolarPreflightRequest,
    PolarPreflightView,
    PolarScanRequest,
    PolarStatusView,
    PreparedClassicSession,
    PARTICIPANT_ID_PATTERN,
    SelectClassicAttempt,
)
from matb_integration.physiology.backend import (
    HEART_RATE_MEASUREMENT_UUID,
    HEART_RATE_SERVICE_UUID,
    PolarBackendError,
)


router = APIRouter(prefix="/classic", tags=["classic"])
_LEASE_HEADER = "X-Classic-Controller"


def get_classic_manager(request: Request) -> ClassicManager:
    manager = getattr(request.app.state, "classic_manager", None)
    if manager is None:
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "classic_unavailable")
    return manager


def _error(status_code: int, code: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": code.replace("_", " ")},
    )


def _lease(value: str | None) -> str:
    if not value:
        raise _error(status.HTTP_403_FORBIDDEN, "classic_invalid_lease")
    return value


def _translate_classic(exc: ClassicRuntimeError) -> HTTPException:
    code = exc.code
    if code == "classic_invalid_lease":
        return _error(status.HTTP_403_FORBIDDEN, code)
    if code in {
        "session_not_found",
        "visit_not_found",
        "participant_not_found",
        "classic_session_not_active",
        "classic_artifact_not_found",
    }:
        return _error(status.HTTP_404_NOT_FOUND, code)
    if code in {
        "classic_active_session",
        "classic_session_already_started",
        "polar_preflight_required",
        "classic_debrief_unavailable",
        "session_immutable",
        "attempt_not_selectable",
    }:
        return _error(status.HTTP_409_CONFLICT, code)
    if code in {
        "classic_scenario_not_available",
        "classic_artifact_path",
        "invalid_workload_level",
        "selection_reason_required",
    }:
        return _error(status.HTTP_422_UNPROCESSABLE_ENTITY, code)
    return _error(status.HTTP_500_INTERNAL_SERVER_ERROR, code)


def _translate_polar(exc: PolarBackendError) -> HTTPException:
    if exc.code in {
        "bleak_unavailable",
        "bluetooth_adapter_unavailable",
        "bluetooth_service_unavailable",
        "bluetooth_adapter_unsupported",
    }:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, exc.code)
    if exc.code in {"device_token_invalid", "device_not_connectable"}:
        return _error(status.HTTP_422_UNPROCESSABLE_ENTITY, exc.code)
    return _error(status.HTTP_409_CONFLICT, exc.code)


@router.get("/polar/capabilities", response_model=PolarCapabilitiesView)
def polar_capabilities(
    manager: ClassicManager = Depends(get_classic_manager),
) -> PolarCapabilitiesView:
    system = platform.system().casefold()
    try:
        bleak_version = importlib.metadata.version("bleak")
    except importlib.metadata.PackageNotFoundError:
        bleak_version = None
    requirements = (
        (
            "Windows 11 build 22000 or later with an enabled BLE adapter",
            "Run the backend in a multithreaded apartment; do not use GUI STA mode",
        )
        if system == "windows"
        else (
            "BlueZ 5.55 or later with bluetoothd and D-Bus available",
            "The service account must have permission to use the system Bluetooth adapter",
        )
        if system == "linux"
        else ("Native acquisition is supported on Windows and Linux only",)
    )
    return PolarCapabilitiesView(
        supported_os=system in {"windows", "linux"},
        platform=system,
        backend_name=manager.polar.status.backend_name,
        bleak_version=bleak_version,
        heart_rate_service_uuid=HEART_RATE_SERVICE_UUID,
        heart_rate_measurement_uuid=HEART_RATE_MEASUREMENT_UUID,
        requirements=requirements,
    )


@router.get("/polar/status", response_model=PolarStatusView)
def polar_status(manager: ClassicManager = Depends(get_classic_manager)) -> PolarStatusView:
    return PolarStatusView.model_validate(asdict(manager.polar.status))


@router.post("/polar/scan", response_model=list[PolarDeviceView])
async def polar_scan(
    body: PolarScanRequest,
    manager: ClassicManager = Depends(get_classic_manager),
) -> list[PolarDeviceView]:
    try:
        candidates = await manager.polar.scan(body.timeout_seconds)
    except PolarBackendError as exc:
        raise _translate_polar(exc) from exc
    return [PolarDeviceView.model_validate(asdict(candidate)) for candidate in candidates]


@router.post("/polar/connect", response_model=PolarStatusView)
async def polar_connect(
    body: PolarConnectRequest,
    manager: ClassicManager = Depends(get_classic_manager),
) -> PolarStatusView:
    try:
        view = await manager.polar.connect(body.device_token)
    except PolarBackendError as exc:
        raise _translate_polar(exc) from exc
    return PolarStatusView.model_validate(asdict(view))


@router.post("/polar/preflight", response_model=PolarPreflightView)
async def polar_preflight(
    body: PolarPreflightRequest,
    manager: ClassicManager = Depends(get_classic_manager),
) -> PolarPreflightView:
    try:
        view = await manager.polar.preflight(timeout_seconds=body.timeout_seconds)
    except PolarBackendError as exc:
        raise _translate_polar(exc) from exc
    return PolarPreflightView.model_validate(asdict(view))


@router.post("/polar/disconnect", response_model=PolarStatusView)
async def polar_disconnect(
    body: EmptyRequest,
    manager: ClassicManager = Depends(get_classic_manager),
) -> PolarStatusView:
    del body
    try:
        view = await manager.polar.disconnect()
    except PolarBackendError as exc:
        raise _translate_polar(exc) from exc
    return PolarStatusView.model_validate(asdict(view))


@router.get("/scenarios", response_model=list[ClassicScenarioView])
def scenarios(manager: ClassicManager = Depends(get_classic_manager)) -> list[ClassicScenarioView]:
    return [
        ClassicScenarioView(
            name=name,
            workload_level=name.rsplit("/", 1)[-1].split("_", 1)[0].upper(),
        )
        for name in manager.scenarios()
    ]


@router.post(
    "/sessions/prepare",
    response_model=PreparedClassicSession,
    status_code=status.HTTP_201_CREATED,
)
async def prepare_session(
    body: CreateClassicSession,
    manager: ClassicManager = Depends(get_classic_manager),
) -> PreparedClassicSession:
    try:
        return await manager.prepare_session(body)
    except ClassicRuntimeError as exc:
        raise _translate_classic(exc) from exc


@router.get("/sessions", response_model=list[ClassicSessionView])
def session_history(
    participant_id: str | None = Query(default=None, pattern=PARTICIPANT_ID_PATTERN),
    visit_ordinal: int | None = Query(default=None, ge=1, le=32),
    manager: ClassicManager = Depends(get_classic_manager),
) -> list[ClassicSessionView]:
    return manager.history(participant_id=participant_id, visit_ordinal=visit_ordinal)


@router.get("/visits/{participant_id}/{visit_ordinal}/summary.{output_format}")
def visit_summary_export(
    participant_id: str,
    visit_ordinal: int,
    output_format: str,
    manager: ClassicManager = Depends(get_classic_manager),
) -> Response:
    try:
        summary = manager.visit_summary(participant_id, visit_ordinal)
    except ClassicRuntimeError as exc:
        raise _translate_classic(exc) from exc
    serializers = {
        "json": (visit_summary_json, "application/json"),
        "csv": (visit_summary_csv, "text/csv; charset=utf-8"),
        "md": (visit_summary_markdown, "text/markdown; charset=utf-8"),
    }
    selected = serializers.get(output_format)
    if selected is None:
        raise _error(status.HTTP_404_NOT_FOUND, "classic_export_format_not_found")
    serializer, media_type = selected
    return Response(
        serializer(summary),
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{participant_id}-visit-{visit_ordinal}-classic-summary.{output_format}"'
            )
        },
    )


@router.get("/sessions/{session_id}", response_model=ClassicSessionView)
def get_session(
    session_id: str,
    manager: ClassicManager = Depends(get_classic_manager),
) -> ClassicSessionView:
    try:
        return manager.session_view(session_id)
    except ClassicRuntimeError as exc:
        raise _translate_classic(exc) from exc


@router.post("/sessions/{session_id}/start", response_model=ClassicSessionView)
async def start_session(
    session_id: str,
    body: EmptyRequest,
    lease: str | None = Header(default=None, alias=_LEASE_HEADER),
    manager: ClassicManager = Depends(get_classic_manager),
) -> ClassicSessionView:
    del body
    try:
        return await manager.start_session(session_id, _lease(lease))
    except ClassicRuntimeError as exc:
        raise _translate_classic(exc) from exc


@router.post("/sessions/{session_id}/abort", response_model=ClassicSessionView)
async def abort_session(
    session_id: str,
    body: AbortClassicSession,
    lease: str | None = Header(default=None, alias=_LEASE_HEADER),
    manager: ClassicManager = Depends(get_classic_manager),
) -> ClassicSessionView:
    try:
        return await manager.abort(session_id, _lease(lease), body.reason_code)
    except ClassicRuntimeError as exc:
        raise _translate_classic(exc) from exc


@router.get("/sessions/{session_id}/debrief", response_model=ClassicDebriefView)
def debrief(
    session_id: str,
    manager: ClassicManager = Depends(get_classic_manager),
) -> ClassicDebriefView:
    try:
        return manager.debrief(session_id)
    except ClassicRuntimeError as exc:
        raise _translate_classic(exc) from exc


@router.get("/sessions/{session_id}/artifacts", response_model=list[ClassicArtifactView])
def artifact_inventory(
    session_id: str,
    manager: ClassicManager = Depends(get_classic_manager),
) -> list[ClassicArtifactView]:
    try:
        return manager.artifacts(session_id)
    except ClassicRuntimeError as exc:
        raise _translate_classic(exc) from exc


def _verified_artifacts(manager: ClassicManager, session_id: str):
    inventory = manager.artifacts(session_id)
    verified = []
    for artifact in inventory:
        path = manager.resolve_artifact(session_id, artifact.relative_path)
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != artifact.sha256:
            raise _error(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "classic_artifact_integrity_failed",
            )
        verified.append((artifact, path, payload))
    if not verified:
        raise _error(status.HTTP_409_CONFLICT, "classic_bundle_unavailable")
    return verified


def _verified_artifact(
    manager: ClassicManager,
    session_id: str,
    relative_path: str,
):
    inventory = {item.relative_path: item for item in manager.artifacts(session_id)}
    artifact = inventory.get(relative_path)
    if artifact is None:
        raise ClassicRuntimeError("classic_artifact_not_found")
    path = manager.resolve_artifact(session_id, relative_path)
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != artifact.sha256:
        raise _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "classic_artifact_integrity_failed",
        )
    return artifact, payload


@router.get("/sessions/{session_id}/bundle")
def download_bundle(
    session_id: str,
    manager: ClassicManager = Depends(get_classic_manager),
) -> Response:
    try:
        verified = _verified_artifacts(manager, session_id)
    except ClassicRuntimeError as exc:
        raise _translate_classic(exc) from exc
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for artifact, _path, payload in verified:
            archive.writestr(artifact.relative_path, payload)
    return Response(
        stream.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="classic-{session_id}.zip"'
        },
    )


@router.get("/sessions/{session_id}/events")
def synchronized_events(
    session_id: str,
    manager: ClassicManager = Depends(get_classic_manager),
) -> Response:
    try:
        _artifact, payload = _verified_artifact(
            manager,
            session_id,
            "openmatb-events.jsonl",
        )
    except ClassicRuntimeError as exc:
        raise _translate_classic(exc) from exc
    return Response(payload, media_type="application/x-ndjson")


@router.get("/sessions/{session_id}/artifacts/{relative_path:path}")
def download_artifact(
    session_id: str,
    relative_path: str,
    manager: ClassicManager = Depends(get_classic_manager),
) -> Response:
    try:
        artifact, payload = _verified_artifact(manager, session_id, relative_path)
    except ClassicRuntimeError as exc:
        raise _translate_classic(exc) from exc
    media_type = (
        "text/markdown; charset=utf-8"
        if relative_path.endswith(".md")
        else "text/csv; charset=utf-8"
        if relative_path.endswith(".csv")
        else "application/json"
        if relative_path.endswith(".json")
        else "application/x-ndjson"
        if relative_path.endswith(".jsonl")
        else "text/plain; charset=utf-8"
    )
    return Response(payload, media_type=media_type)


@router.post("/sessions/{session_id}/select", response_model=ClassicSessionView)
def select_attempt(
    session_id: str,
    body: SelectClassicAttempt,
    manager: ClassicManager = Depends(get_classic_manager),
) -> ClassicSessionView:
    try:
        return manager.select_attempt(session_id, body.reason_code)
    except ClassicRuntimeError as exc:
        raise _translate_classic(exc) from exc


__all__ = ["get_classic_manager", "router"]
