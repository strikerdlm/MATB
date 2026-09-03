import { getApiBase } from "@/lib/runtime-config";
import type {
  PolarCapabilities,
  PolarAnalysis,
  PolarCapture,
  PolarConnection,
  PolarDevice,
  PolarEvent,
  PreparedPolarCapture,
} from "@/types/physiology";

const PREFIX = "/physiology/polar-h10/v1";

export class PolarApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
    this.name = "PolarApiError";
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const base = await getApiBase();
  const response = await fetch(`${base}${PREFIX}${path}`, init);
  if (!response.ok) {
    let code = "polar_request_failed";
    let message = response.statusText;
    try {
      const payload = await response.json();
      code = payload?.detail?.code ?? code;
      message = payload?.detail?.message ?? message;
    } catch { /* retain HTTP fallback */ }
    throw new PolarApiError(response.status, code, message);
  }
  return response.json() as Promise<T>;
}

const post = (body: object, lease?: string): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json", ...(lease ? { "X-Polar-Controller": lease } : {}) },
  body: JSON.stringify(body),
});

export const scanPolar = (timeoutSeconds = 5) =>
  call<PolarDevice[]>("/scan", post({ timeout_seconds: timeoutSeconds }));
export const listenPolarBroadcast = (timeoutSeconds = 5) =>
  call<PolarDevice[]>("/broadcast/scan", post({ timeout_seconds: timeoutSeconds }));
export const connectPolar = (deviceToken: string) =>
  call<PolarCapabilities>("/connect", post({ device_token: deviceToken }));
export const getPolarConnection = () => call<PolarConnection>("/connection");
export const disconnectPolar = () => call<PolarConnection>("/connection", { method: "DELETE" });

export function createPolarCapture(body: {
  participant_pseudonym: string;
  matb_session_kind: PolarCapture["matb_session_kind"];
  matb_session_id: string;
  settings: {
    ecg_sample_rate_hz: 130;
    ecg_resolution_bits: 14;
    acc_sample_rate_hz: 25 | 50 | 100 | 200;
    acc_resolution_bits: 16;
    acc_range_g: 2 | 4 | 8;
  };
}) {
  return call<PreparedPolarCapture>("/captures", post(body));
}

export const startPolarCapture = (id: string, lease: string) =>
  call<PolarCapture>(`/captures/${encodeURIComponent(id)}/start`, post({}, lease));
export const stopPolarCapture = (id: string, lease: string) =>
  call<PolarCapture>(`/captures/${encodeURIComponent(id)}/stop`, post({}, lease));
export const addPolarMarker = (id: string, lease: string, label: string) =>
  call<PolarCapture>(`/captures/${encodeURIComponent(id)}/markers`, post({ label, payload: {} }, lease));
export const getPolarAnalysis = (id: string, lease: string) =>
  call<PolarAnalysis>(`/captures/${encodeURIComponent(id)}/analysis`, {
    headers: { "X-Polar-Controller": lease },
  });

export async function downloadPolarBundle(id: string, lease: string): Promise<void> {
  const base = await getApiBase();
  const response = await fetch(`${base}${PREFIX}/captures/${encodeURIComponent(id)}/bundle`, {
    headers: { "X-Polar-Controller": lease },
  });
  if (!response.ok) throw new PolarApiError(response.status, "polar_bundle_failed", response.statusText);
  const objectUrl = URL.createObjectURL(await response.blob());
  try {
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = `${id}.zip`;
    anchor.click();
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

export async function openPolarStream(
  id: string,
  lease: string,
  afterSequence: number,
  onEvent: (event: PolarEvent) => void,
  onState: (capture: PolarCapture) => void,
): Promise<WebSocket> {
  const base = new URL(await getApiBase());
  base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
  base.pathname = `${PREFIX}/captures/${encodeURIComponent(id)}/stream`;
  base.searchParams.set("lease", lease);
  base.searchParams.set("after_sequence", String(afterSequence));
  const socket = new WebSocket(base.toString());
  socket.addEventListener("message", (message) => {
    const payload = JSON.parse(String(message.data));
    if (payload.kind === "event") onEvent(payload as PolarEvent);
    if (payload.kind === "capture_state") onState(payload.capture as PolarCapture);
  });
  return socket;
}
