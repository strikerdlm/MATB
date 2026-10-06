"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, Check, Loader2 } from "lucide-react";
import { CrewFrame } from "./CrewFrame";
import { CrewDaySummary, activityNames, testDate } from "./CrewDaySummary";
import { crewActivity, crewHref, getCrewProgress, prepareCrewActivity, type CrewPreparation, type CrewProgress } from "@/lib/crew-workflow";
import { EXPERIMENTS } from "@/lib/experiments";
import { useAppLocale } from "@/lib/i18n";
import { controllerAction, createOpenMatbSession, getOpenMatbDisplays, getOpenMatbReadiness, getOpenMatbSession, readOpenMatbController, readOpenMatbParticipant, recoverPendingOpenMatbSession, startOpenMatbAsParticipant, storeOpenMatbCredentials } from "@/lib/openmatb/api";
import { openMatbErrorMessage } from "@/lib/openmatb/errors";
import { createSimulationSession } from "@/lib/simulation/api";
import { storePreparedSessionLease } from "@/lib/simulation/lease";

export function CrewSelector() {
  const query = useSearchParams();
  const activity = crewActivity(query.get("experiment"));
  const requestedCrew = query.get("crew") ?? "";
  const router = useRouter();
  const { copy, locale } = useAppLocale();
  const [people, setPeople] = useState<CrewProgress[]>([]);
  const [selected, setSelected] = useState(requestedCrew);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [rest, setRest] = useState(0);
  const locked = useRef(false);
  const generation = useRef(0);
  const person = people.find(row => row.callsign === selected);
  const experiment = EXPERIMENTS.find(row => row.id === activity)!;
  const refresh = useCallback(async () => {
    const current = ++generation.current;
    setLoading(true);
    try {
      const result = await getCrewProgress(activity);
      if (current === generation.current) { setPeople(result.participants); setError(""); }
    } catch (reason) {
      if (current === generation.current) setError(reason instanceof Error ? reason.message : String(reason));
    } finally { if (current === generation.current) setLoading(false); }
  }, [activity]);
  useEffect(() => { setSelected(requestedCrew); setRest(0); setMessage(""); void refresh(); return () => { generation.current += 1; }; }, [refresh, requestedCrew]);
  useEffect(() => {
    const timer = window.setInterval(() => setRest(value => Math.max(0, value - 1)), 1000);
    const onFocus = () => { if (!locked.current) void refresh(); };
    window.addEventListener("focus", onFocus);
    return () => { window.clearInterval(timer); window.removeEventListener("focus", onFocus); };
  }, [refresh]);

  async function openNative(prepared: CrewPreparation) {
    const [ready, displays] = await Promise.all([getOpenMatbReadiness(), getOpenMatbDisplays()]);
    if (!ready.ready || !displays.length) throw new Error(copy("La estación necesita revisar OpenMATB, audio o controles antes de abrir la prueba.", "The station needs to check OpenMATB, audio or controls before opening the test."));
    let sessionId = prepared.session_id;
    if (!sessionId) {
      const config = prepared.config!;
      if (!config.preset || !config.instructions || !config.visual) throw new Error("Configuración OpenMATB incompleta.");
      const created = await createOpenMatbSession({ preparation_only: true, attempt_id: prepared.attempt_id,
        execution_purpose: "study", participant_id: prepared.participant_id, visit_ordinal: prepared.visit_ordinal!,
        preset_id: config.preset.id, preset_version: config.preset.version,
        instruction_protocol_id: config.instructions.id, instruction_version: config.instructions.version,
        visual_profile_id: config.visual.id, visual_profile_version: config.visual.version,
        display_index: displays.find(row => row.index === 0)?.index ?? displays[0].index });
      storeOpenMatbCredentials(created);
      sessionId = created.session.id;
    }
    let session = await getOpenMatbSession(sessionId);
    let lease = readOpenMatbController(sessionId);
    let token = readOpenMatbParticipant(sessionId);
    if ((!lease || !token) && ["INSTRUCTIONS", "READY", "PREFLIGHT_READY"].includes(session.lifecycle)) {
      const recovered = await recoverPendingOpenMatbSession(sessionId);
      storeOpenMatbCredentials(recovered);
      lease = recovered.controller_lease; token = recovered.participant_token;
      session = recovered.session;
    }
    if (!token || !lease) throw new Error(copy("La prueba ya está abierta. Continúa en la pestaña donde comenzó.", "The test is already open. Continue in its original tab."));
    if (session.lifecycle === "PREFLIGHT_READY") {
      setMessage(copy("Comprobando la pantalla y los controles…", "Checking display and controls…"));
      session = await controllerAction(sessionId, "preflight", lease);
    }
    if (session.lifecycle === "PREFLIGHT_HELD") await startOpenMatbAsParticipant(sessionId, token, session.current_block_index);
    router.push(`/openmatb/participant?session=${encodeURIComponent(sessionId)}&crew=${encodeURIComponent(prepared.callsign)}`);
  }

  async function begin() {
    if (!person || locked.current || rest > 0) return;
    locked.current = true; setBusy(true); setError("");
    setMessage(copy("Preparando tu prueba…", "Preparing your test…"));
    try {
      // Check tab storage before creating a runtime whose control token must survive navigation.
      sessionStorage.setItem("crew.storage-check", "ok"); sessionStorage.removeItem("crew.storage-check");
      const target = person.state === "activity_complete" ? person.next_activity ?? activity : activity;
      const next = await prepareCrewActivity(person.callsign, target, person.state === "interrupted");
      if (next.action === "rest") {
        setRest(Math.ceil(next.remaining_seconds ?? 0));
        setMessage(copy("Pausa entre bloques. La siguiente prueba estará disponible al terminar.", "Rest between blocks. The next task will be available when it ends."));
      } else if (["scheduled", "activity_complete", "complete", "needs_review"].includes(next.action)) {
        await refresh(); setMessage("");
      } else if (next.action === "retry_required") {
        if (target !== activity) {
          router.push(crewHref(target, person.callsign));
          return;
        }
        await refresh(); setMessage(copy("La prueba anterior se interrumpió. Puedes reintentar la sesión pendiente.", "The previous test was interrupted. You can retry the pending session."));
      } else if (next.action === "native_session" || next.activity === "openmatb") {
        await openNative(next);
      } else if (next.activity === "suas") {
        let sessionId = next.session_id;
        if (!sessionId) {
          const created = await createSimulationSession({ attempt_id: next.attempt_id, execution_purpose: "study",
            participant_id: next.participant_id, visit_ordinal: next.visit_ordinal!, scenario_id: next.config!.scenario!.id,
            locale: next.locale === "en" ? "en" : "es-CO", ...(next.config?.presentation ? { presentation: next.config.presentation } : {}) });
          await storePreparedSessionLease(created); sessionId = created.id;
        }
        router.push(`/mission?session=${encodeURIComponent(sessionId)}&crew=${encodeURIComponent(next.callsign)}`);
      } else {
        const destination = new URLSearchParams({ attempt: next.attempt_id!, crew: next.callsign, return: target });
        router.push(`/study/run?${destination}`);
      }
    } catch (reason) {
      setMessage("");
      setError(activity === "openmatb" ? openMatbErrorMessage(reason, copy) : reason instanceof Error ? reason.message : String(reason));
    } finally { locked.current = false; setBusy(false); }
  }

  const done = person?.state === "scheduled" || person?.state === "complete";
  return <CrewFrame>
    <div className="crew-heading"><h1>{copy("¿Quién va a realizar la prueba?", "Who is taking the test?")}</h1><p>{copy(...experiment.title)}</p></div>
    {error && <div role="alert" className="crew-error"><p>{error}</p><button type="button" onClick={() => void refresh()} disabled={busy}>{copy("Volver a comprobar", "Check again")}</button></div>}
    {loading && !people.length ? <p role="status" className="crew-loading">{copy("Cargando tripulación…", "Loading crew…")}</p> : <div className="crew-columns">
      <div className="crew-list" role="group" aria-label={copy("Tripulantes", "Crew members")}>
        {people.map(row => <button type="button" key={row.callsign} aria-pressed={row.callsign === selected} disabled={busy} onClick={() => { setSelected(row.callsign); setRest(0); setMessage(""); setError(""); }}>
          <span>{row.callsign}</span>{row.callsign === selected && <Check aria-hidden="true" size={26} />}
        </button>)}
      </div>
      <section className="crew-detail" aria-live="polite" aria-busy={busy}>
        {!person ? <div className="crew-empty"><p>{copy("Elige tu callsign para continuar.", "Choose your callsign to continue.")}</p></div> : <>
          <h2>{person.callsign}</h2>
          <div className="crew-session">
            <p className="crew-muted">{person.state === "scheduled" ? copy("Próxima jornada", "Next test day") : person.state === "complete" ? copy("Misión completada", "Mission complete") : copy("Tu jornada", "Your test day")}</p>
            <h3>{person.state === "complete" ? copy("Todas las pruebas guardadas", "All tests saved") : `${person.day_label} · ${testDate(person.scheduled_date, locale)}`}</h3>
            <p>{person.state === "scheduled" ? copy("Tus pruebas se abrirán en esta fecha.", "Your tests will open on this date.") : person.state === "complete" ? copy("Completaste las tres jornadas en misión y la postmisión.", "You completed all three mission test days and the post-mission test day.") : person.message ?? (person.state === "activity_complete" ? copy("Esta prueba ya está guardada. Continúa con la siguiente pendiente.", "This test is saved. Continue with the next pending test.") : person.state === "interrupted" ? copy("Retomarás la prueba pendiente; el intento anterior se conserva.", "You will return to the pending test; the previous attempt is retained.") : copy("Cada prueba se guarda a tu nombre.", "Every test is saved under your callsign."))}</p>
          </div>
          {!done && <button className="crew-primary" type="button" disabled={busy || loading || rest > 0 || person.state === "needs_review"} onClick={() => void begin()}>
            {busy ? <><Loader2 className="animate-spin" aria-hidden="true" size={22} />{copy("Abriendo prueba…", "Opening test…")}</> : rest > 0 ? `${copy("Pausa", "Rest")} · ${Math.floor(rest / 60)}:${String(rest % 60).padStart(2, "0")}` : <>{person.state === "interrupted" ? copy("Reintentar prueba", "Retry test") : person.state === "activity_complete" && person.next_activity ? copy(`Continuar: ${activityNames[person.next_activity][0]}`, `Continue: ${activityNames[person.next_activity][1]}`) : copy("Comenzar prueba", "Start test")}<ArrowRight aria-hidden="true" size={26} /></>}
          </button>}
          {message ? <p role="status" className="crew-note">{message}</p> : !done && <p className="crew-note">{copy("La prueba se abrirá automáticamente.", "The test will open automatically.")}</p>}
          <CrewDaySummary person={person} />
        </>}
      </section>
    </div>}
  </CrewFrame>;
}
