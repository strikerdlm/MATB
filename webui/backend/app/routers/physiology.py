"""Local, controller-leased Polar H10 acquisition API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse

from app.physiology_runtime import PolarCaptureManager, PolarRuntimeError
from app.physiology_schemas import (
    ArtifactInventory,
    ConnectRequest,
    ConnectionView,
    CreateCaptureRequest,
    EmptyRequest,
    InternalRecordingGate,
    MarkerRequest,
    PhysiologyAnalysisView,
    PolarDeviceView,
    PreparedCapture,
    ScanRequest,
)
from matb_integration.physiology.contracts import PolarCaptureV1, PolarDeviceCapabilitiesV1


router = APIRouter(prefix="/physiology/polar-h10/v1", tags=["polar-h10"])
_CONTROLLER = "X-Polar-Controller"


def manager(request: Request) -> PolarCaptureManager:
    value = getattr(request.app.state, "polar_manager", None)
    if value is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "polar_component_unavailable", "message": "Polar component is unavailable"},
        )
    return value


def _lease(value: str | None) -> str:
    if not value:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"code": "polar_controller_lease_required", "message": "Polar controller lease is required"},
        )
    return value


def _translate(exc: PolarRuntimeError) -> HTTPException:
    if exc.code in {"polar_invalid_controller_lease", "invalid_or_expired_device_token"}:
        code = status.HTTP_403_FORBIDDEN
    elif exc.code.endswith("_not_found") or exc.code == "participant_not_found":
        code = status.HTTP_404_NOT_FOUND
    elif exc.code in {
        "polar_component_unavailable", "polar_connection_failed", "polar_scan_failed",
        "bluetooth_unavailable",
    }:
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif exc.code in {"exact_stream_settings_unavailable", "mandatory_stream_unavailable"}:
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        code = status.HTTP_409_CONFLICT
    return HTTPException(
        code,
        detail={"code": exc.code, "message": exc.code.replace("_", " "), "context": exc.context},
    )


async def _managed(call):
    try:
        return await call()
    except PolarRuntimeError as exc:
        raise _translate(exc) from exc


def _managed_sync(call):
    try:
        return call()
    except PolarRuntimeError as exc:
        raise _translate(exc) from exc


def _device_views(entries: list[tuple[str, object]]) -> list[PolarDeviceView]:
    output: list[PolarDeviceView] = []
    for token, candidate in entries:
        broadcast = candidate.broadcast
        output.append(PolarDeviceView(
            device_token=token,
            alias=candidate.alias,
            connectable=candidate.connectable,
            rssi=candidate.rssi,
            broadcast_hr_bpm=broadcast.heart_rate_bpm if broadcast else None,
            broadcast_contact=broadcast.sensor_contact if broadcast else None,
            token_expires_in_seconds=PolarCaptureManager.DEVICE_TOKEN_TTL_SECONDS,
        ))
    return output


@router.post("/scan", response_model=list[PolarDeviceView])
async def scan(body: ScanRequest, runtime: PolarCaptureManager = Depends(manager)):
    return _device_views(await _managed(lambda: runtime.scan(body.timeout_seconds)))


@router.post("/broadcast/scan", response_model=list[PolarDeviceView])
async def broadcast_scan(body: ScanRequest, runtime: PolarCaptureManager = Depends(manager)):
    """Bounded listen-only preflight; broadcast HR is not an HRV source."""

    return _device_views(await _managed(lambda: runtime.scan(body.timeout_seconds)))


@router.post("/connect", response_model=PolarDeviceCapabilitiesV1)
async def connect(body: ConnectRequest, runtime: PolarCaptureManager = Depends(manager)):
    return await _managed(lambda: runtime.connect(body.device_token))


@router.get("/connection", response_model=ConnectionView)
def connection(runtime: PolarCaptureManager = Depends(manager)):
    alias, capabilities = runtime.connection()
    return ConnectionView(connected=alias is not None, device_alias=alias, capabilities=capabilities)


@router.delete("/connection", response_model=ConnectionView)
async def disconnect(runtime: PolarCaptureManager = Depends(manager)):
    await _managed(lambda: runtime.disconnect())
    return ConnectionView(connected=False, device_alias=None, capabilities=None)


@router.post("/captures", response_model=PreparedCapture, status_code=status.HTTP_201_CREATED)
def create_capture(body: CreateCaptureRequest, runtime: PolarCaptureManager = Depends(manager)):
    capture, lease = _managed_sync(lambda: runtime.create_capture(
        participant_id=body.participant_pseudonym,
        session_kind=body.matb_session_kind,
        session_id=body.matb_session_id,
        settings=body.settings.model_dump(),
    ))
    return PreparedCapture(capture=capture, controller_lease=lease)


@router.post("/captures/{capture_id}/start", response_model=PolarCaptureV1)
async def start_capture(
    capture_id: str,
    body: EmptyRequest,
    controller: str | None = Header(default=None, alias=_CONTROLLER),
    runtime: PolarCaptureManager = Depends(manager),
):
    del body
    return await _managed(lambda: runtime.start_capture(capture_id, _lease(controller)))


@router.post("/captures/{capture_id}/markers", response_model=PolarCaptureV1)
async def marker(
    capture_id: str,
    body: MarkerRequest,
    controller: str | None = Header(default=None, alias=_CONTROLLER),
    runtime: PolarCaptureManager = Depends(manager),
):
    return await _managed(lambda: runtime.add_marker(
        capture_id, _lease(controller), body.label, body.payload
    ))


@router.post("/captures/{capture_id}/stop", response_model=PolarCaptureV1)
async def stop_capture(
    capture_id: str,
    body: EmptyRequest,
    controller: str | None = Header(default=None, alias=_CONTROLLER),
    runtime: PolarCaptureManager = Depends(manager),
):
    del body
    return await _managed(lambda: runtime.stop_capture(capture_id, _lease(controller)))


@router.get("/captures/{capture_id}", response_model=PolarCaptureV1)
def capture(capture_id: str, runtime: PolarCaptureManager = Depends(manager)):
    return _managed_sync(lambda: runtime.capture_view(capture_id))


@router.get("/captures/{capture_id}/artifacts", response_model=ArtifactInventory)
def artifacts(
    capture_id: str,
    controller: str | None = Header(default=None, alias=_CONTROLLER),
    runtime: PolarCaptureManager = Depends(manager),
):
    row, manifest, partials = _managed_sync(
        lambda: runtime.inventory(capture_id, _lease(controller))
    )
    return ArtifactInventory(
        capture_id=capture_id, state=row.artifact_state, manifest=manifest, partial_files=partials
    )


@router.get("/captures/{capture_id}/bundle")
def bundle(
    capture_id: str,
    controller: str | None = Header(default=None, alias=_CONTROLLER),
    runtime: PolarCaptureManager = Depends(manager),
):
    path = _managed_sync(lambda: runtime.bundle(capture_id, _lease(controller)))
    return FileResponse(path, filename=path.name, media_type="application/zip")


@router.get("/captures/{capture_id}/analysis", response_model=PhysiologyAnalysisView)
def analysis(
    capture_id: str,
    controller: str | None = Header(default=None, alias=_CONTROLLER),
    runtime: PolarCaptureManager = Depends(manager),
):
    return _managed_sync(lambda: runtime.analyze_capture(capture_id, _lease(controller)))


@router.websocket("/captures/{capture_id}/stream")
async def capture_stream(websocket: WebSocket, capture_id: str) -> None:
    origin = websocket.headers.get("origin")
    if origin is None or origin not in websocket.app.state.frontend_origins:
        await websocket.close(code=4403)
        return
    runtime = getattr(websocket.app.state, "polar_manager", None)
    if runtime is None:
        await websocket.close(code=4503)
        return
    lease = websocket.query_params.get("lease", "")
    try:
        after = int(websocket.query_params.get("after_sequence", "0"))
        if after < 0:
            raise ValueError
        runtime.validate_lease(capture_id, lease)
    except ValueError:
        await websocket.close(code=4400)
        return
    except PolarRuntimeError as exc:
        await websocket.close(code=4403 if exc.code == "polar_invalid_controller_lease" else 4404)
        return
    await websocket.accept()
    try:
        await websocket.send_json({"kind": "capture_state", "capture": runtime.capture_view(capture_id).model_dump(mode="json")})
        while True:
            events = await runtime.events_after(capture_id, after, timeout_s=20.0)
            if not events:
                await websocket.send_json({"kind": "heartbeat", "after_sequence": after})
                continue
            for event in events:
                await websocket.send_json({"kind": "event", **event.model_dump(mode="json")})
                after = event.sequence
    except WebSocketDisconnect:
        return


def _internal_gate() -> InternalRecordingGate:
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        detail=InternalRecordingGate().model_dump(),
    )


@router.get("/internal-recordings/status", response_model=InternalRecordingGate)
def internal_status():
    return _internal_gate()


@router.get("/internal-recordings", response_model=InternalRecordingGate)
def internal_list():
    return _internal_gate()


@router.post("/internal-recordings/start", response_model=InternalRecordingGate)
def internal_start(body: EmptyRequest):
    del body
    return _internal_gate()


@router.post("/internal-recordings/stop", response_model=InternalRecordingGate)
def internal_stop(body: EmptyRequest):
    del body
    return _internal_gate()


@router.post("/internal-recordings/{recording_id}/fetch", response_model=InternalRecordingGate)
def internal_fetch(recording_id: str, body: EmptyRequest):
    del recording_id, body
    return _internal_gate()


@router.delete("/internal-recordings/{recording_id}", response_model=InternalRecordingGate)
def internal_remove(recording_id: str):
    del recording_id
    return _internal_gate()
