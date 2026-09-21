"use client";
import { useEffect, useRef, useState } from "react";
import type { PresentationConfig } from "./contracts";
import { initialPresentation, presentationReducer, type PresentationAction, type ResolvedPresentation } from "./state";
import { ExposureQueue, presentationQueues as queues } from "./queue";
import { sendPresentationEvent, getSimulationSession } from "../api";
import { useSimulationStore } from "../store";

type Context = { sessionId: string; block: string; lease?: string | null; config?: PresentationConfig | null;
  time: number; stateVersion: number; trafficFrame?: string | null; replay: boolean; active: boolean };
type RecordEvent = Parameters<typeof sendPresentationEvent>[2];
// Session-owned state survives the participant surface being unmounted for SAGAT.
const retained = new Map<string, ResolvedPresentation>();
const failures = new Map<string, string>();
let sequence = 0;
export function usePresentation(context: Context) {
  const key = `${context.sessionId}:${context.block}`;
  const [state, setState] = useState(() => retained.get(key) ?? initialPresentation(context.config, context.block,
    typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches));
  const [error, setError] = useState<string | null>(failures.get(context.sessionId) ?? null);
  const current = useRef(context); current.current = context;
  const latest = useRef(state);
  const keyRef = useRef(key);
  if (keyRef.current !== key) {
    keyRef.current = key;
    latest.current = retained.get(key) ?? initialPresentation(context.config, context.block);
    setState(latest.current);
  }
  const record = (kind: string, resolved = latest.current, elapsed?: number) => {
    const c = current.current;
    const live = useSimulationStore.getState().session;
    if (live?.id === c.sessionId && ["FINISHED", "ABORTED", "INTERRUPTED"].includes(live.lifecycle)) return;
    if (c.replay || !c.lease || !c.active || (c.config?.version ?? 1) < 2) return;
    const makeEvent = (eventKind: string): RecordEvent => ({
      version: c.config?.version, event_id: crypto.randomUUID(), kind: eventKind, block_id: c.block,
      sequence: sequence = Math.max(sequence + 1, Math.floor((performance.timeOrigin + performance.now()) * 1000)),
      client_time_ms: performance.timeOrigin + performance.now(), simulation_time_ms: c.time,
      state_version: c.stateVersion, traffic_frame_id: c.trafficFrame ?? null,
      scene_sha256: c.config?.scene_sha256 ?? null, camera: resolved.camera,
      resolved: structuredClone(resolved), ...(elapsed === undefined ? {} : { receipt_to_render_ms: elapsed }),
    });
    let queue = queues.get(c.sessionId);
    if (!queue) {
      const sessionId = c.sessionId, lease = c.lease;
      queue = new ExposureQueue(async item => {
        await sendPresentationEvent(sessionId, lease, item);
        if (item.kind === "failure") useSimulationStore.setState({ session: await getSimulationSession(sessionId) });
      }, reason => {
        failures.set(sessionId, String(reason));
        setError(String(reason));
        const failure = { ...makeEvent("failure"), resolved: { ...latest.current, visibility: "unavailable" } };
        void sendPresentationEvent(sessionId, lease, failure).then(async () => {
          useSimulationStore.setState({ session: await getSimulationSession(sessionId) });
        }).catch(() => { /* Local controls remain blocked if the transport is unavailable. */ });
      });
      queues.set(c.sessionId, queue);
    }
    queue.push(makeEvent(kind));
  };
  const dispatch = (action: PresentationAction, kind: string = action.type) => {
    const store = useSimulationStore.getState();
    if (!current.current.replay && store.session?.id === current.current.sessionId && store.concealOperationalState && kind !== "visibility") return;
    latest.current = presentationReducer(latest.current, action);
    if (!current.current.replay) {
      retained.set(`${current.current.sessionId}:${current.current.block}`, latest.current);
      if (retained.size > 16) retained.delete(retained.keys().next().value!);
    }
    setState(latest.current);
    record(kind);
  };
  const callbacks = useRef({ record, dispatch }); callbacks.current = { record, dispatch };
  useEffect(() => {
    callbacks.current.dispatch({ type: "resolved", patch: { visibility: document.hidden ? "hidden" : "visible" } }, "visibility");
    const changed = () => callbacks.current.dispatch({ type: "resolved", patch: { visibility: document.hidden ? "hidden" : "visible" } }, "visibility");
    document.addEventListener("visibilitychange", changed);
    return () => {
      document.removeEventListener("visibilitychange", changed);
      const concealed = useSimulationStore.getState().concealOperationalState;
      latest.current = { ...latest.current, visibility: concealed ? "concealed" : "hidden" };
      callbacks.current.record("visibility", latest.current);
    };
  }, [key]);
  return { state, latest, dispatch, record, error: error ?? failures.get(context.sessionId) ?? null };
}
