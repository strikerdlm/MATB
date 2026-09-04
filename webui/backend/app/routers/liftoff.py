"""Guarded REST surface for Liftoff collection."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from app.liftoff_runtime import LiftoffManager, LiftoffRuntimeError
from app.liftoff_schemas import (
    AbortRequest,
    CreateLiftoffSession,
    EmptyRequest,
    LiftoffArtifactView,
    LiftoffDebriefView,
    LiftoffProtocolView,
    LiftoffReadinessView,
    LiftoffSessionView,
    PhysiologyLinkView,
    PreparedLiftoffSession,
    QuestionnairesRequest,
    VisibleResultsRequest,
)
from app.study_protocol import selected_protocol
from matb_integration.liftoff.protocol import LIFTOFF_ALL_V1

router = APIRouter(prefix="/liftoff", tags=["liftoff"])
_LEASE_HEADER = "X-Liftoff-Controller"
_MAX_SCREENSHOT_BYTES = 10 * 1024 * 1024


def get_liftoff_manager(request: Request) -> LiftoffManager:
    manager = getattr(request.app.state, "liftoff_manager", None)
    if manager is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "liftoff_unavailable", "message": "Liftoff runtime is unavailable"},
        )
    return manager


def _lease(value: str | None) -> str:
    if value is None or not value:
        raise _error(status.HTTP_403_FORBIDDEN, "liftoff_invalid_lease")
    return value


def _error(status_code: int, code: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": code.replace("_", " ")},
    )


def _translate(exc: LiftoffRuntimeError) -> HTTPException:
    code = exc.code
    if code == "liftoff_invalid_lease":
        return _error(status.HTTP_403_FORBIDDEN, code)
    if code in {
        "participant_not_found",
        "visit_not_found",
        "liftoff_session_not_found",
        "liftoff_session_not_active",
    }:
        return _error(status.HTTP_404_NOT_FOUND, code)
    if code in {
        "study_context_required", "assigned_matb_first",
        "liftoff_telemetry_not_ready",
        "liftoff_active_session",
        "liftoff_retake_not_allowed",
        "liftoff_phase_order",
        "liftoff_visible_results_required",
        "liftoff_questionnaires_required",
        "liftoff_session_not_finished",
        "liftoff_debrief_unavailable",
        "liftoff_bundle_unavailable",
    }:
        return _error(status.HTTP_409_CONFLICT, code)
    if code in {"liftoff_visit_not_in_protocol", "liftoff_artifact_path"}:
        return _error(status.HTTP_422_UNPROCESSABLE_ENTITY, code)
    if code in {
        "liftoff_hrv_metadata_invalid",
        "liftoff_hrv_identity_mismatch",
        "liftoff_phase_markers_incomplete",
        "liftoff_hrv_contract_rejected",
        "liftoff_hrv_response_mismatch",
    }:
        return _error(status.HTTP_422_UNPROCESSABLE_ENTITY, code)
    if code in {"liftoff_hrv_pending_not_found"}:
        return _error(status.HTTP_404_NOT_FOUND, code)
    return _error(status.HTTP_500_INTERNAL_SERVER_ERROR, code)


def _managed(call):
    try:
        return call()
    except LiftoffRuntimeError as exc:
        raise _translate(exc) from exc


async def _managed_async(call):
    try:
        return await call()
    except LiftoffRuntimeError as exc:
        raise _translate(exc) from exc


@router.get("/protocol", response_model=LiftoffProtocolView)
def protocol_view() -> LiftoffProtocolView:
    protocol = selected_protocol()
    return LiftoffProtocolView(
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.protocol_version,
        schedule_sha256=protocol.schedule_sha256,
        telemetry_profile=LIFTOFF_ALL_V1,
        visits=[
            {
                "ordinal": visit.ordinal,
                "code": visit.code,
                "scheduled_day": visit.scheduled_day,
            }
            for visit in protocol.visits
        ],
    )


@router.get("/readiness", response_model=LiftoffReadinessView)
def readiness(manager: LiftoffManager = Depends(get_liftoff_manager)) -> LiftoffReadinessView:
    return manager.readiness_view()


@router.post("/sessions", response_model=PreparedLiftoffSession, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: CreateLiftoffSession,
    manager: LiftoffManager = Depends(get_liftoff_manager),
) -> PreparedLiftoffSession:
    return await _managed_async(lambda: manager.create_session(body))


@router.get("/sessions/{session_id}", response_model=LiftoffSessionView)
def get_session(
    session_id: str,
    manager: LiftoffManager = Depends(get_liftoff_manager),
) -> LiftoffSessionView:
    return _managed(lambda: manager.session_view(session_id))


async def _transition(
    session_id: str,
    action: str,
    lease: str | None,
    manager: LiftoffManager,
) -> LiftoffSessionView:
    return await _managed_async(
        lambda: manager.transition(session_id, action, _lease(lease))  # type: ignore[arg-type]
    )


@router.post("/sessions/{session_id}/baseline/start", response_model=LiftoffSessionView)
async def baseline_start(session_id: str, body: EmptyRequest, lease: str | None = Header(default=None, alias=_LEASE_HEADER), manager: LiftoffManager = Depends(get_liftoff_manager)):
    del body
    return await _transition(session_id, "baseline/start", lease, manager)


@router.post("/sessions/{session_id}/baseline/finish", response_model=LiftoffSessionView)
async def baseline_finish(session_id: str, body: EmptyRequest, lease: str | None = Header(default=None, alias=_LEASE_HEADER), manager: LiftoffManager = Depends(get_liftoff_manager)):
    del body
    return await _transition(session_id, "baseline/finish", lease, manager)


@router.post("/sessions/{session_id}/task/start", response_model=LiftoffSessionView)
async def task_start(session_id: str, body: EmptyRequest, lease: str | None = Header(default=None, alias=_LEASE_HEADER), manager: LiftoffManager = Depends(get_liftoff_manager)):
    del body
    return await _transition(session_id, "task/start", lease, manager)


@router.post("/sessions/{session_id}/task/finish", response_model=LiftoffSessionView)
async def task_finish(session_id: str, body: EmptyRequest, lease: str | None = Header(default=None, alias=_LEASE_HEADER), manager: LiftoffManager = Depends(get_liftoff_manager)):
    del body
    return await _transition(session_id, "task/finish", lease, manager)


@router.post("/sessions/{session_id}/recovery/start", response_model=LiftoffSessionView)
async def recovery_start(session_id: str, body: EmptyRequest, lease: str | None = Header(default=None, alias=_LEASE_HEADER), manager: LiftoffManager = Depends(get_liftoff_manager)):
    del body
    return await _transition(session_id, "recovery/start", lease, manager)


@router.post("/sessions/{session_id}/recovery/finish", response_model=LiftoffSessionView)
async def recovery_finish(session_id: str, body: EmptyRequest, lease: str | None = Header(default=None, alias=_LEASE_HEADER), manager: LiftoffManager = Depends(get_liftoff_manager)):
    del body
    return await _transition(session_id, "recovery/finish", lease, manager)


@router.post("/sessions/{session_id}/abort", response_model=LiftoffSessionView)
def abort_session(
    session_id: str,
    body: AbortRequest,
    lease: str | None = Header(default=None, alias=_LEASE_HEADER),
    manager: LiftoffManager = Depends(get_liftoff_manager),
) -> LiftoffSessionView:
    return _managed(lambda: manager.abort(session_id, _lease(lease), body.reason_code))


@router.post("/sessions/{session_id}/results", status_code=status.HTTP_201_CREATED)
async def submit_results(
    session_id: str,
    metadata: str = Form(...),
    screenshot: UploadFile = File(...),
    lease: str | None = Header(default=None, alias=_LEASE_HEADER),
    manager: LiftoffManager = Depends(get_liftoff_manager),
) -> dict[str, str]:
    try:
        request = VisibleResultsRequest.model_validate_json(metadata)
    except ValidationError as exc:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "liftoff_results_invalid") from exc
    image = await screenshot.read(_MAX_SCREENSHOT_BYTES + 1)
    if len(image) > _MAX_SCREENSHOT_BYTES:
        raise _error(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "liftoff_screenshot_too_large")
    is_png = image.startswith(b"\x89PNG\r\n\x1a\n")
    is_jpeg = image.startswith(b"\xff\xd8\xff")
    if screenshot.content_type not in {"image/png", "image/jpeg"} or not (is_png or is_jpeg):
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "liftoff_screenshot_type")
    if hashlib.sha256(image).hexdigest() != request.screenshot_sha256:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "liftoff_screenshot_hash")
    _managed(lambda: manager.submit_results(session_id, _lease(lease), request, image))
    return {"status": "recorded"}


@router.post("/sessions/{session_id}/questionnaires", status_code=status.HTTP_201_CREATED)
def submit_questionnaires(
    session_id: str,
    body: QuestionnairesRequest,
    lease: str | None = Header(default=None, alias=_LEASE_HEADER),
    manager: LiftoffManager = Depends(get_liftoff_manager),
) -> dict[str, str]:
    _managed(lambda: manager.submit_questionnaires(session_id, _lease(lease), body))
    return {"status": "recorded"}


@router.post("/sessions/{session_id}/physiology-link", response_model=PhysiologyLinkView)
async def attach_physiology(
    session_id: str,
    rr_file: UploadFile = File(...),
    metadata_file: UploadFile = File(...),
    lease: str | None = Header(default=None, alias=_LEASE_HEADER),
    manager: LiftoffManager = Depends(get_liftoff_manager),
) -> PhysiologyLinkView | JSONResponse:
    rr_bytes = await rr_file.read(5_000_001)
    metadata_bytes = await metadata_file.read(131_073)
    if len(rr_bytes) > 5_000_000 or len(metadata_bytes) > 131_072:
        raise _error(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "liftoff_hrv_upload_too_large")
    try:
        rr_content = rr_bytes.decode("utf-8")
        metadata = json.loads(metadata_bytes.decode("utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "liftoff_hrv_upload_invalid") from exc
    try:
        view = await manager.analyze_physiology(
            session_id,
            _lease(lease),
            rr_content=rr_content,
            metadata=metadata,
        )
    except LiftoffRuntimeError as exc:
        raise _translate(exc) from exc
    if view.status == "pending":
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=view.model_dump(mode="json"))
    return view


@router.post(
    "/sessions/{session_id}/physiology-link/retry",
    response_model=PhysiologyLinkView,
)
async def retry_physiology(
    session_id: str,
    body: EmptyRequest,
    lease: str | None = Header(default=None, alias=_LEASE_HEADER),
    manager: LiftoffManager = Depends(get_liftoff_manager),
) -> PhysiologyLinkView | JSONResponse:
    del body
    try:
        view = await manager.retry_physiology(session_id, _lease(lease))
    except LiftoffRuntimeError as exc:
        raise _translate(exc) from exc
    if view.status == "pending":
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=view.model_dump(mode="json"))
    return view


@router.post("/sessions/{session_id}/seal", response_model=LiftoffDebriefView)
def seal_session(
    session_id: str,
    body: EmptyRequest,
    lease: str | None = Header(default=None, alias=_LEASE_HEADER),
    manager: LiftoffManager = Depends(get_liftoff_manager),
) -> LiftoffDebriefView:
    del body
    return _managed(lambda: manager.seal(session_id, _lease(lease)))


@router.get("/sessions/{session_id}/debrief", response_model=LiftoffDebriefView)
def debrief(
    session_id: str,
    manager: LiftoffManager = Depends(get_liftoff_manager),
) -> LiftoffDebriefView:
    return _managed(lambda: manager.debrief_view(session_id))


@router.get("/sessions/{session_id}/artifacts", response_model=list[LiftoffArtifactView])
def artifacts(
    session_id: str,
    manager: LiftoffManager = Depends(get_liftoff_manager),
) -> list[LiftoffArtifactView]:
    return _managed(lambda: manager.artifact_views(session_id))


@router.get("/sessions/{session_id}/bundle")
def bundle(
    session_id: str,
    manager: LiftoffManager = Depends(get_liftoff_manager),
) -> Response:
    if _managed(lambda: manager.session_view(session_id)).execution_purpose == "practice":
        raise HTTPException(409, detail={"code": "practice_not_research_export"})
    root, artifact_rows = _managed(lambda: manager.bundle_files(session_id))
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for artifact in artifact_rows:
            path = root / artifact.relative_path
            archive.writestr(artifact.relative_path, path.read_bytes())
    return Response(
        output.getvalue(),
        media_type="application/zip",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="liftoff-{session_id}.zip"',
        },
    )


__all__ = ["get_liftoff_manager", "router"]
