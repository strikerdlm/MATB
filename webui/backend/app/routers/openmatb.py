"""Local API for the frontend-supervised native OpenMATB suite."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.openmatb_runtime import OpenMatbManager, OpenMatbRuntimeError
from app.openmatb_schemas import (
    AbortRequest,
    CloneInstructionRequest,
    ClonePresetRequest,
    CloneVisualProfileRequest,
    CreateOpenMatbSession,
    EmptyRequest,
    ParticipantReadyRequest,
    ImportVisualProfileRequest,
    InstructionProtocolView,
    OpenMatbReadiness,
    OpenMatbSessionView,
    OpenMatbVisualProfileView,
    PreparedOpenMatbSession,
    PresetSetView,
    PublishVisualProfileRequest,
    UpdateInstructionRequest,
    UpdatePresetRequest,
    UpdateVisualProfileRequest,
    VisualProfilePreviewRequest,
    VisualProfilePreviewView,
    WorkloadScaleRequest,
)

router = APIRouter(prefix="/openmatb", tags=["openmatb"])
_CONTROLLER = "X-OpenMATB-Controller"
_PARTICIPANT = "X-OpenMATB-Participant"

_ERROR_MESSAGES = {
    "openmatb_active_session": "A session is already prepared on this station. Resume or close it before creating another.",
    "openmatb_ready_block_changed": "The displayed block changed. Refresh the session before starting.",
    "openmatb_recovery_not_pending": "Only a session that has not started can be recovered from another tab. Use the original control tab for an active task.",
    "openmatb_dependency_missing": "OpenMATB dependencies are missing. Run the Windows preparation launcher, then try again.",
    "openmatb_launch_failed": "OpenMATB closed before its participant window was ready. Review the station checks and service logs.",
    "openmatb_ready_timeout": "OpenMATB did not report a ready participant window within 20 seconds.",
    "openmatb_job_assignment_failed": "Windows could not attach OpenMATB to the supervised process group.",
}


def manager(request: Request) -> OpenMatbManager:
    value = getattr(request.app.state, "openmatb_manager", None)
    if value is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "openmatb_unavailable", "message": "OpenMATB controller is unavailable"})
    return value


def _required(value: str | None, code: str) -> str:
    if not value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": code, "message": code.replace("_", " ")})
    return value


def _translate(exc: OpenMatbRuntimeError) -> HTTPException:
    if exc.code in {"openmatb_invalid_lease", "openmatb_invalid_participant_token"}:
        code = status.HTTP_403_FORBIDDEN
    elif exc.code.endswith("_not_found") or exc.code in {"participant_not_found", "visit_not_found"}:
        code = status.HTTP_404_NOT_FOUND
    elif exc.code in {
        "openmatb_dependency_missing",
        "openmatb_job_assignment_failed",
        "openmatb_launch_failed",
        "openmatb_ready_timeout",
        "openmatb_unavailable",
    }:
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        code = status.HTTP_409_CONFLICT
    message = _ERROR_MESSAGES.get(exc.code, exc.code.replace("_", " "))
    return HTTPException(code, detail={"code": exc.code, "message": message})


def _managed(call):
    try:
        return call()
    except OpenMatbRuntimeError as exc:
        raise _translate(exc) from exc


async def _managed_async(call):
    try:
        return await call()
    except OpenMatbRuntimeError as exc:
        raise _translate(exc) from exc


@router.get("/readiness", response_model=OpenMatbReadiness)
def readiness(runtime: OpenMatbManager = Depends(manager)):
    return runtime.readiness()


@router.get("/presets", response_model=list[PresetSetView])
def presets(runtime: OpenMatbManager = Depends(manager)):
    return runtime.list_presets()


@router.post("/presets/{source_id}/{source_version}/clone", response_model=PresetSetView, status_code=201)
def clone_preset(source_id: str, source_version: str, body: ClonePresetRequest, runtime: OpenMatbManager = Depends(manager)):
    return _managed(lambda: runtime.clone_preset(source_id, source_version, body))


@router.put("/presets/{preset_id}/{version}", response_model=PresetSetView)
def update_preset(preset_id: str, version: str, body: UpdatePresetRequest, runtime: OpenMatbManager = Depends(manager)):
    return _managed(lambda: runtime.update_preset(preset_id, version, body))


@router.post("/presets/{preset_id}/{version}/publish", response_model=PresetSetView)
def publish_preset(preset_id: str, version: str, body: EmptyRequest, runtime: OpenMatbManager = Depends(manager)):
    del body
    return _managed(lambda: runtime.publish_preset(preset_id, version))


@router.get("/instruction-protocols", response_model=list[InstructionProtocolView])
def instruction_protocols(runtime: OpenMatbManager = Depends(manager)):
    return runtime.list_instructions()


@router.post("/instruction-protocols/{source_id}/{source_version}/clone", response_model=InstructionProtocolView, status_code=201)
def clone_instructions(source_id: str, source_version: str, body: CloneInstructionRequest, runtime: OpenMatbManager = Depends(manager)):
    return _managed(lambda: runtime.clone_instructions(source_id, source_version, body))


@router.put("/instruction-protocols/{protocol_id}/{version}", response_model=InstructionProtocolView)
def update_instructions(protocol_id: str, version: str, body: UpdateInstructionRequest, runtime: OpenMatbManager = Depends(manager)):
    return _managed(lambda: runtime.update_instructions(protocol_id, version, body))


@router.post("/instruction-protocols/{protocol_id}/{version}/publish", response_model=InstructionProtocolView)
def publish_instructions(protocol_id: str, version: str, body: EmptyRequest, runtime: OpenMatbManager = Depends(manager)):
    del body
    return _managed(lambda: runtime.publish_instructions(protocol_id, version))


@router.get("/visual-profiles", response_model=list[OpenMatbVisualProfileView])
def visual_profiles(runtime: OpenMatbManager = Depends(manager)):
    return _managed(runtime.list_visual_profiles)


@router.post("/visual-profiles/import", response_model=OpenMatbVisualProfileView, status_code=201)
def import_visual_profile(body: ImportVisualProfileRequest, runtime: OpenMatbManager = Depends(manager)):
    return _managed(lambda: runtime.import_visual_profile(body))


@router.get("/visual-profiles/preview", response_model=VisualProfilePreviewView)
def visual_profile_preview(runtime: OpenMatbManager = Depends(manager)):
    return runtime.visual_profile_preview_status()


@router.post("/visual-profiles/preview/abort", response_model=VisualProfilePreviewView)
async def abort_visual_profile_preview(body: EmptyRequest, runtime: OpenMatbManager = Depends(manager)):
    del body
    return await _managed_async(runtime.abort_visual_profile_preview)


@router.get("/visual-profiles/{profile_id}/{version}", response_model=OpenMatbVisualProfileView)
def visual_profile(profile_id: str, version: str, runtime: OpenMatbManager = Depends(manager)):
    return _managed(lambda: runtime.get_visual_profile(profile_id, version))


@router.post(
    "/visual-profiles/{source_id}/{source_version}/clone",
    response_model=OpenMatbVisualProfileView,
    status_code=201,
)
def clone_visual_profile(
    source_id: str,
    source_version: str,
    body: CloneVisualProfileRequest,
    runtime: OpenMatbManager = Depends(manager),
):
    return _managed(lambda: runtime.clone_visual_profile(source_id, source_version, body))


@router.put("/visual-profiles/{profile_id}/{version}", response_model=OpenMatbVisualProfileView)
def update_visual_profile(
    profile_id: str,
    version: str,
    body: UpdateVisualProfileRequest,
    runtime: OpenMatbManager = Depends(manager),
):
    return _managed(lambda: runtime.update_visual_profile(profile_id, version, body))


@router.post("/visual-profiles/{profile_id}/{version}/validate", response_model=OpenMatbVisualProfileView)
def validate_visual_profile(
    profile_id: str,
    version: str,
    body: EmptyRequest,
    runtime: OpenMatbManager = Depends(manager),
):
    del body
    return _managed(lambda: runtime.validate_saved_visual_profile(profile_id, version))


@router.post("/visual-profiles/{profile_id}/{version}/publish", response_model=OpenMatbVisualProfileView)
def publish_visual_profile(
    profile_id: str,
    version: str,
    body: PublishVisualProfileRequest,
    runtime: OpenMatbManager = Depends(manager),
):
    return _managed(lambda: runtime.publish_visual_profile(profile_id, version, body))


@router.get("/visual-profiles/{profile_id}/{version}/export")
def export_visual_profile(
    profile_id: str,
    version: str,
    runtime: OpenMatbManager = Depends(manager),
):
    document = _managed(lambda: runtime.export_visual_profile(profile_id, version))
    return JSONResponse(
        content=document.model_dump(mode="json"),
        headers={"Content-Disposition": 'attachment; filename="openmatb-visual-profile.json"'},
    )


@router.post(
    "/visual-profiles/{profile_id}/{version}/preview",
    response_model=VisualProfilePreviewView,
)
async def start_visual_profile_preview(
    profile_id: str,
    version: str,
    body: VisualProfilePreviewRequest,
    runtime: OpenMatbManager = Depends(manager),
):
    return await _managed_async(lambda: runtime.start_visual_profile_preview(profile_id, version, body))


@router.post("/sessions", response_model=PreparedOpenMatbSession, status_code=201)
async def create_session(body: CreateOpenMatbSession, runtime: OpenMatbManager = Depends(manager)):
    return await _managed_async(lambda: runtime.create_session(body))


@router.get("/sessions/active", response_model=OpenMatbSessionView | None)
def active_session(runtime: OpenMatbManager = Depends(manager)):
    return _managed(runtime.active_session)


@router.post("/sessions/{session_id}/recover", response_model=PreparedOpenMatbSession)
async def recover_pending_session(session_id: str, body: EmptyRequest, runtime: OpenMatbManager = Depends(manager)):
    return await _managed_async(lambda: runtime.recover_pending_session(session_id))


@router.get("/sessions/{session_id}", response_model=OpenMatbSessionView)
def get_session(session_id: str, runtime: OpenMatbManager = Depends(manager)):
    return _managed(lambda: runtime.session_view(session_id))


@router.get("/displays")
def displays(runtime: OpenMatbManager = Depends(manager)):
    return _managed(runtime.displays)


@router.get("/sessions/{session_id}/receipt")
def receipt(session_id: str, runtime: OpenMatbManager = Depends(manager)):
    return _managed(lambda: runtime.receipt(session_id))


@router.post("/sessions/{session_id}/blocks/{block_instance_id}/evidence/retry")
async def retry_evidence(session_id: str, block_instance_id: str, body: EmptyRequest,
                         lease: str | None = Header(default=None, alias=_CONTROLLER),
                         runtime: OpenMatbManager = Depends(manager)):
    return await _managed_async(lambda: runtime.retry_evidence(session_id, block_instance_id,
        _required(lease, "openmatb_controller_required")))


@router.post("/sessions/{session_id}/instructions/acknowledge", response_model=OpenMatbSessionView)
def acknowledge(session_id: str, body: EmptyRequest, token: str | None = Header(default=None, alias=_PARTICIPANT), runtime: OpenMatbManager = Depends(manager)):
    del body
    return _managed(lambda: runtime.acknowledge_instructions(session_id, _required(token, "openmatb_participant_token_required")))


@router.post("/sessions/{session_id}/start", response_model=OpenMatbSessionView)
async def start(session_id: str, body: EmptyRequest, request: Request, lease: str | None = Header(default=None, alias=_CONTROLLER), runtime: OpenMatbManager = Depends(manager)):
    del body
    result = await _managed_async(lambda: runtime.start_block(session_id, _required(lease, "openmatb_controller_required")))
    physiology = getattr(request.app.state, "polar_manager", None)
    if physiology is not None and result.active_block is not None:
        await physiology.system_marker_for_session(
            "openmatb", session_id, result.active_block,
            {"block_index": result.current_block_index, "automatic": True},
        )
    return result


@router.post("/sessions/{session_id}/participant-ready", response_model=OpenMatbSessionView)
async def participant_ready(session_id: str, body: ParticipantReadyRequest, request: Request,
                            token: str | None = Header(default=None, alias=_PARTICIPANT),
                            runtime: OpenMatbManager = Depends(manager)):
    result, changed = await _managed_async(lambda: runtime.participant_ready(
        session_id, _required(token, "openmatb_participant_token_required"), body.block_index))
    physiology = getattr(request.app.state, "polar_manager", None)
    if physiology is not None and changed and result.active_block is not None:
        await physiology.system_marker_for_session(
            "openmatb", session_id, result.active_block,
            {"block_index": result.current_block_index, "automatic": True},
        )
    return result


@router.post("/sessions/{session_id}/pause", response_model=OpenMatbSessionView)
async def pause(session_id: str, body: EmptyRequest, lease: str | None = Header(default=None, alias=_CONTROLLER), runtime: OpenMatbManager = Depends(manager)):
    del body
    return await _managed_async(lambda: runtime.pause(session_id, _required(lease, "openmatb_controller_required")))


@router.post("/sessions/{session_id}/resume", response_model=OpenMatbSessionView)
async def resume(session_id: str, body: EmptyRequest, lease: str | None = Header(default=None, alias=_CONTROLLER), runtime: OpenMatbManager = Depends(manager)):
    del body
    return await _managed_async(lambda: runtime.resume(session_id, _required(lease, "openmatb_controller_required")))


@router.post("/sessions/{session_id}/repeat-practice", response_model=OpenMatbSessionView)
def repeat_practice(session_id: str, body: EmptyRequest, lease: str | None = Header(default=None, alias=_CONTROLLER), runtime: OpenMatbManager = Depends(manager)):
    del body
    return _managed(lambda: runtime.repeat_practice(session_id, _required(lease, "openmatb_controller_required")))


@router.post("/sessions/{session_id}/abort", response_model=OpenMatbSessionView)
async def abort(session_id: str, body: AbortRequest, request: Request, lease: str | None = Header(default=None, alias=_CONTROLLER), runtime: OpenMatbManager = Depends(manager)):
    result = await _managed_async(lambda: runtime.abort(session_id, _required(lease, "openmatb_controller_required"), body.reason))
    physiology = getattr(request.app.state, "polar_manager", None)
    if physiology is not None:
        await physiology.system_marker_for_session("openmatb", session_id, "ABORTED", {"reason": body.reason})
    return result


@router.post("/sessions/{session_id}/scales", response_model=OpenMatbSessionView)
async def submit_scales(session_id: str, body: WorkloadScaleRequest, request: Request, token: str | None = Header(default=None, alias=_PARTICIPANT), runtime: OpenMatbManager = Depends(manager)):
    result, changed = _managed(lambda: runtime.submit_scale_once(session_id, _required(token, "openmatb_participant_token_required"), body))
    physiology = getattr(request.app.state, "polar_manager", None)
    if physiology is not None and changed:
        label = "RECOVERY" if result.lifecycle == "COMPLETE" else "BETWEEN_BLOCKS"
        await physiology.system_marker_for_session(
            "openmatb", session_id, label,
            {"completed_block_index": max(0, result.current_block_index - 1), "automatic": True},
        )
    return result


@router.post('/sessions/{session_id}/preflight', response_model=OpenMatbSessionView)
async def preflight(session_id: str, body: EmptyRequest, lease: str | None = Header(default=None, alias=_CONTROLLER), runtime: OpenMatbManager = Depends(manager)):
    return await _managed_async(lambda: runtime.start_block(session_id, _required(lease, 'openmatb_controller_required'), preparation_only=True))
