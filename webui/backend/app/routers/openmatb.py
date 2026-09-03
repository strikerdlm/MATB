"""Local API for the frontend-supervised classic OpenMATB suite."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.openmatb_runtime import OpenMatbManager, OpenMatbRuntimeError
from app.openmatb_schemas import (
    AbortRequest,
    CloneInstructionRequest,
    ClonePresetRequest,
    CreateOpenMatbSession,
    EmptyRequest,
    InstructionProtocolView,
    OpenMatbReadiness,
    OpenMatbSessionView,
    PreparedOpenMatbSession,
    PresetSetView,
    UpdateInstructionRequest,
    UpdatePresetRequest,
    WorkloadScaleRequest,
)

router = APIRouter(prefix="/openmatb", tags=["openmatb"])
_CONTROLLER = "X-OpenMATB-Controller"
_PARTICIPANT = "X-OpenMATB-Participant"


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
    elif exc.code in {"openmatb_ready_timeout", "openmatb_unavailable"}:
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        code = status.HTTP_409_CONFLICT
    return HTTPException(code, detail={"code": exc.code, "message": exc.code.replace("_", " ")})


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


@router.post("/sessions", response_model=PreparedOpenMatbSession, status_code=201)
async def create_session(body: CreateOpenMatbSession, runtime: OpenMatbManager = Depends(manager)):
    return await _managed_async(lambda: runtime.create_session(body))


@router.get("/sessions/{session_id}", response_model=OpenMatbSessionView)
def get_session(session_id: str, runtime: OpenMatbManager = Depends(manager)):
    return _managed(lambda: runtime.session_view(session_id))


@router.post("/sessions/{session_id}/instructions/acknowledge", response_model=OpenMatbSessionView)
def acknowledge(session_id: str, body: EmptyRequest, token: str | None = Header(default=None, alias=_PARTICIPANT), runtime: OpenMatbManager = Depends(manager)):
    del body
    return _managed(lambda: runtime.acknowledge_instructions(session_id, _required(token, "openmatb_participant_token_required")))


@router.post("/sessions/{session_id}/start", response_model=OpenMatbSessionView)
async def start(session_id: str, body: EmptyRequest, lease: str | None = Header(default=None, alias=_CONTROLLER), runtime: OpenMatbManager = Depends(manager)):
    del body
    return await _managed_async(lambda: runtime.start_block(session_id, _required(lease, "openmatb_controller_required")))


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
async def abort(session_id: str, body: AbortRequest, lease: str | None = Header(default=None, alias=_CONTROLLER), runtime: OpenMatbManager = Depends(manager)):
    return await _managed_async(lambda: runtime.abort(session_id, _required(lease, "openmatb_controller_required"), body.reason))


@router.post("/sessions/{session_id}/scales", response_model=OpenMatbSessionView)
def submit_scales(session_id: str, body: WorkloadScaleRequest, token: str | None = Header(default=None, alias=_PARTICIPANT), runtime: OpenMatbManager = Depends(manager)):
    return _managed(lambda: runtime.submit_scale(session_id, _required(token, "openmatb_participant_token_required"), body))
