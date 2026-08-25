import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent, JSX, ReactNode } from "react";
import { EdgeApiClient, EdgeApiError, SessionExpiredError } from "../api/client.js";
import type { AuthenticatedSession, GateName, MissionView, SignedMissionExport, TelemetryRecord, UserRole } from "../api/types.js";
import { getLabels, type Locale } from "../i18n/registry.js";
import { emptyMissionScopedState, isOperationalSafeModeFailure, missionRevisionChanged, RequestEpoch, type MissionScopedState, type OperationalData } from "./operational-state.js";
import { errorLabel, operatorLabel } from "./operator-labels.js";

export interface AppShellProps { readonly initialPath?: string; readonly initialLocale?: Locale; readonly apiClient?: EdgeApiClient }
type ConnectionState = "loading" | "connected" | "disconnected" | "forbidden" | "safe-mode";
type LockState = "idle" | "pending" | "unconfirmed";
type Labels = ReturnType<typeof getLabels>;
type Message = { readonly key: keyof Labels } | { readonly text: string };
type RunOperation = (operation: (signal: AbortSignal) => Promise<unknown>, success: Message) => Promise<void>;
const GATES: readonly GateName[] = ["maintenance", "operator", "safety", "commander"];
const ROLE_FOR_GATE: Readonly<Record<GateName, UserRole | "safety">> = { maintenance: "maintainer", operator: "operator", safety: "safety", commander: "commander" };
const DEFERRED = [["fleet", "fleet"], ["planning", "planning"], ["assurance", "assurance"], ["research", "research"], ["reportsModule", "reports"], ["documentsModule", "documents"], ["notesModule", "notes"]] as const;
const GATE_ROLES: readonly UserRole[] = ["maintainer", "operator", "safety-officer", "commander", "reviewer"];

function isAbort(error: unknown): boolean { return error instanceof DOMException && error.name === "AbortError"; }
function messageText(message: Message, labels: Labels): string { return "key" in message ? String(labels[message.key]) : message.text; }
function probeDelay(session: AuthenticatedSession): number {
  const idleDeadline = Date.parse(session.lastActivityAtUtc) + session.idleTimeoutMs;
  const hardDeadline = Date.parse(session.expiresAtUtc);
  const remaining = Math.min(idleDeadline, hardDeadline) - Date.now();
  return Math.max(1_000, Math.min(30_000, Math.floor(session.idleTimeoutMs / 3), Number.isFinite(remaining) ? remaining : 1_000));
}
function displayCheck(labels: Labels, value: string): string {
  const checks: Readonly<Record<string, keyof Labels>> = { database: "databaseCheck", migrations: "migrationsCheck", audit: "auditCheck", tls: "tlsCheck", exportKey: "exportKeyCheck", trustAnchors: "trustAnchorsCheck", activeTerminology: "activeTerminologyCheck", activePolicy: "activePolicyCheck", bootstrapAdministrator: "bootstrapAdministratorCheck" };
  const key = checks[value]; return key === undefined ? value : String(labels[key]);
}
function readinessDetail(labels: Labels, detail?: string): string { return detail === undefined ? "" : ` — ${labels.notReady}`; }

export function AppShell({ initialLocale = "en", apiClient }: AppShellProps): JSX.Element {
  const client = useMemo(() => apiClient ?? new EdgeApiClient(), [apiClient]);
  const requests = useMemo(() => new RequestEpoch(), []);
  const loadRequests = useMemo(() => new RequestEpoch(), []);
  const writes = useMemo(() => new RequestEpoch(), []);
  const safeModeRef = useRef(false);
  const [locale, setLocale] = useState<Locale>(initialLocale);
  const [night, setNight] = useState(true);
  const [scope, setScope] = useState<MissionScopedState>(() => emptyMissionScopedState());
  const [connection, setConnection] = useState<ConnectionState>("disconnected");
  const [message, setMessage] = useState<Message>({ key: "signInTitle" });
  const [lockState, setLockState] = useState<LockState>("idle");
  const labels = getLabels(locale);
  const { session, data, selectedMissionId, signedExport } = scope;
  const mission = data?.missions.missions.find(({ missionId }) => missionId === selectedMissionId) ?? data?.missions.missions[0];
  const readOnly = connection === "safe-mode";

  const clearSensitive = useCallback((nextMessage: Message, forgetSession: boolean) => {
    requests.invalidate(); loadRequests.invalidate(); writes.invalidate(); safeModeRef.current = false; if (forgetSession) client.forgetSession(); setScope(emptyMissionScopedState()); setConnection("disconnected"); setMessage(nextMessage);
  }, [client, loadRequests, requests, writes]);

  const resetSession = useCallback((nextMessage: Message) => { setLockState("idle"); clearSensitive(nextMessage, true); }, [clearSensitive]);

  const enterSafeMode = useCallback(() => {
    safeModeRef.current = true; writes.invalidate(); setConnection("safe-mode"); setMessage({ key: "readOnlySafeMode" });
  }, [writes]);

  const clearForError = useCallback((error: unknown) => {
    resetSession(error instanceof SessionExpiredError ? { key: "sessionExpired" } : error instanceof EdgeApiError ? { text: errorLabel(labels, error.code) } : { key: "edgeDisconnected" });
  }, [labels, resetSession]);

  const loadData = useCallback(async (active: AuthenticatedSession): Promise<boolean> => {
    const ticket = loadRequests.beginLatest(); setConnection("loading"); setMessage({ key: "loadingAuthoritative" });
    try {
      const [missions, packages, readiness, audit] = await Promise.all([
        client.get<OperationalData["missions"]>("/api/missions", ticket.signal), client.get<OperationalData["packages"]>("/api/packages", ticket.signal),
        client.readiness(ticket.signal), client.get<OperationalData["audit"]>("/api/audit/health", ticket.signal),
      ]);
      if (!ticket.isCurrent()) return false;
      const safeMode = audit.state === "safe-mode" || Object.values(readiness.checks).some(({ detail }) => detail?.includes("read-only"));
      safeModeRef.current = safeMode; if (safeMode) writes.invalidate();
      const nextData = { missions, packages, readiness, audit };
      setScope((current) => { if (current.session?.sessionId !== active.sessionId) return current; const nextSelected = missions.missions.some(({ missionId }) => missionId === current.selectedMissionId) ? current.selectedMissionId : missions.missions[0]?.missionId; return { ...current, session: active, data: nextData, selectedMissionId: nextSelected, signedExport: missionRevisionChanged(current.data, nextData, nextSelected) ? undefined : current.signedExport }; });
      setConnection(safeMode ? "safe-mode" : "connected"); setMessage({ key: safeMode ? "readOnlySafeMode" : "connectedEdge" }); return true;
    } catch (error) {
      if (isAbort(error) || !ticket.isCurrent()) return false;
      if (error instanceof EdgeApiError && isOperationalSafeModeFailure(error.status, error.code)) { enterSafeMode(); return false; }
      if (error instanceof EdgeApiError && error.status === 403) { setConnection("forbidden"); setMessage({ key: "forbiddenRole" }); return false; }
      clearForError(error); return false;
    } finally { ticket.finish(); }
  }, [client, clearForError, enterSafeMode, loadRequests, writes]);

  const beginPrincipal = useCallback(async (active: AuthenticatedSession): Promise<void> => {
    requests.invalidate(); loadRequests.invalidate(); writes.invalidate(); safeModeRef.current = false; setLockState("idle"); setScope({ ...emptyMissionScopedState(), session: active }); await loadData(active);
  }, [loadData, loadRequests, requests, writes]);

  const validateSession = useCallback(async (): Promise<void> => {
    const current = client.session(); if (current === undefined) { clearForError(new SessionExpiredError()); return; }
    const ticket = requests.begin();
    try {
      const status = await client.sessionStatus(ticket.signal);
      if (!ticket.isCurrent() || status.sessionId !== current.sessionId) return;
      setScope((value) => value.session?.sessionId === status.sessionId ? { ...value, session: { ...value.session, ...status } } : value);
    } catch (error) { if (!isAbort(error) && ticket.isCurrent()) clearForError(error); }
    finally { ticket.finish(); }
  }, [client, clearForError, requests]);

  // Keep the scheduler tied only to server-provided deadlines. Locale/message
  // changes may replace the validation callback, but must never postpone an
  // already scheduled idle-expiry probe.
  const validateSessionRef = useRef(validateSession);
  validateSessionRef.current = validateSession;

  useEffect(() => {
    if (session === undefined) return;
    let active = true; let timer: number | undefined;
    const probe = async () => { await validateSessionRef.current(); const current = client.session(); if (active && current !== undefined) timer = window.setTimeout(() => { void probe(); }, probeDelay(current)); };
    timer = window.setTimeout(() => { void probe(); }, probeDelay(session));
    return () => { active = false; if (timer !== undefined) window.clearTimeout(timer); };
  }, [client, session?.expiresAtUtc, session?.idleTimeoutMs, session?.lastActivityAtUtc, session?.sessionId]);
  useEffect(() => () => { requests.invalidate(); loadRequests.invalidate(); writes.invalidate(); }, [loadRequests, requests, writes]);

  const run = useCallback<RunOperation>(async (operation, success) => {
    if (safeModeRef.current) { setMessage({ key: "readOnlyBlocked" }); return; }
    const principalGeneration = requests.snapshot(); const ticket = writes.begin();
    try {
      await operation(ticket.signal);
      if (!ticket.isCurrent() || !requests.isCurrent(principalGeneration)) return;
      setMessage(success); const active = client.session(); if (active !== undefined) await loadData(active);
    } catch (error) {
      if (isAbort(error) || !ticket.isCurrent() || !requests.isCurrent(principalGeneration)) return;
      if (error instanceof SessionExpiredError) clearForError(error);
      else if (error instanceof EdgeApiError && isOperationalSafeModeFailure(error.status, error.code)) enterSafeMode();
      else if (error instanceof EdgeApiError && error.status === 403) { setConnection("forbidden"); setMessage({ text: errorLabel(labels, error.code) }); }
      else if (error instanceof EdgeApiError) setMessage({ text: errorLabel(labels, error.code) });
      else setMessage({ key: "requestFailed" });
    } finally { ticket.finish(); }
  }, [client, clearForError, enterSafeMode, labels, loadData, requests, writes]);

  const lock = useCallback(async () => {
    const active = client.session(); if (active === undefined) { resetSession({ key: "locked" }); return; }
    setLockState("pending"); clearSensitive({ key: "lockPending" }, false);
    try { await client.lock(active.sessionId); setLockState("idle"); setMessage({ key: "locked" }); }
    catch (error) { if (error instanceof SessionExpiredError) { setLockState("idle"); setMessage({ key: "locked" }); } else { setLockState("unconfirmed"); setMessage({ key: "lockUnconfirmed" }); } }
  }, [clearSensitive, client, resetSession]);
  const selectMission = useCallback((missionId: string) => {
    writes.invalidate(); setScope((value) => value.selectedMissionId === missionId ? value : { ...value, selectedMissionId: missionId, signedExport: undefined });
  }, [writes]);

  if (session === undefined) return <LoginScreen client={client} connection={connection} labels={labels} lockState={lockState} message={messageText(message, labels)} locale={locale} onLocale={() => setLocale(locale === "en" ? "es" : "en")} onLogin={beginPrincipal} onRetryLock={() => { void lock(); }} />;
  const safety = mission?.safetyResults.find(({ revisionId }) => revisionId === mission.currentRevisionId);
  const stale = safety?.stale === true;
  const blocked = safety === undefined || stale || safety.status !== "ready";
  const canManage = session.roles.some((role) => role === "commander" || role === "safety-officer");
  return <div className={`console-shell live-console ${night ? "theme-night" : "theme-day"}`}>
    <aside className="side-rail" aria-label={labels.primaryNavigation}><Brand labels={labels} /><nav aria-label={labels.missionNavigation} className="live-nav">
      <a href="#mission">{labels.overview}</a><a href="#safety">{labels.safetyReview}</a><a href="#checklists">{labels.checklistNav}</a><a href="#gates">{labels.gatesNav}</a><a href="#telemetry">{labels.telemetry}</a><a href="#system">{labels.systemNav}</a>
    </nav><div className="deferred-list" aria-label={labels.deferredModules} tabIndex={0}>{DEFERRED.map(([key, fallback]) => <button disabled key={key} type="button"><span>{String(labels[key] ?? fallback)}</span><small>{labels.deferredRelease}</small></button>)}</div></aside>
    <main className="main-frame live-main"><header className="top-bar live-topbar"><div><strong>{session.userId}</strong><span>{session.roles.map((role) => operatorLabel(labels, role)).join(" · ")}</span></div><div className="top-controls"><Status state={connection}>{messageText(message, labels)}</Status>
      <button aria-label={labels.changeLanguage} className="locale-toggle" onClick={() => setLocale(locale === "en" ? "es" : "en")} type="button">{locale.toUpperCase()} / {locale === "en" ? "ES" : "EN"}</button>
      <button aria-label={labels.toggleTheme} className="theme-toggle" onClick={() => setNight((value) => !value)} type="button">{night ? labels.day : labels.night}</button><button onClick={() => { void lock(); }} type="button">{labels.lock}</button></div></header>
      <div className="classification-banner">{labels.unclassified}</div>
      <section className="live-grid" id="mission" aria-labelledby="missions-heading"><article className="ops-card mission-list"><h1 id="missions-heading">{labels.missions}</h1>{data === undefined ? <StateBlock labels={labels} state="loading" /> : data.missions.missions.length === 0 ? <StateBlock labels={labels} state="blocked" detail={labels.noAssignedMissions} /> : data.missions.missions.map((item) => <button className={item.missionId === mission?.missionId ? "selected" : ""} key={item.missionId} onClick={() => selectMission(item.missionId)} type="button"><strong>{item.missionId}</strong><span>{labels.revision} {item.currentRevision.revision} · {operatorLabel(labels, item.currentRevision.state)}</span></button>)}<MissionCreator canManage={canManage} labels={labels} readOnly={readOnly} client={client} run={run} /></article>
        <MissionRevision mission={mission} canManage={canManage} labels={labels} readOnly={readOnly} client={client} run={run} /></section>
      <section className={`ops-card safety-card state-${stale ? "stale" : blocked ? "blocked" : "api-ready"}`} id="safety" aria-labelledby="safety-heading"><div className="card-heading"><div><span>{labels.serverOwnedEvaluation}</span><h2 id="safety-heading">{labels.missionStrip}</h2></div><Status state={stale ? "stale" : blocked ? "blocked" : "api-ready"}>{stale ? labels.stale : safety === undefined ? labels.unavailable : operatorLabel(labels, safety.status)}</Status></div>
        {safety === undefined ? <StateBlock labels={labels} state="safe-mode" detail={labels.safetyUnavailable} /> : <><dl className="facts"><Fact label={labels.revision} value={safety.revisionId} /><Fact label={labels.evaluated} value={safety.evaluatedAtUtc ?? labels.apiTimeUnavailable} /><Fact label={labels.status} value={operatorLabel(labels, safety.status)} /></dl>{safety.blockers.length === 0 ? <p>{labels.noSafetyBlockers}</p> : <ul>{safety.blockers.map((item, index) => <li key={`${item.code}-${index}`}><strong>{item.code}</strong> {item.explanation ?? labels.serverBlocker}</li>)}</ul>}</>}
      </section>
      <Checklist mission={mission} labels={labels} readOnly={readOnly} client={client} run={run} /><GateGrid mission={mission} session={session} blocked={blocked} labels={labels} readOnly={readOnly} client={client} run={run} />
      <TelemetryBoundary key={`${session.sessionId}:${mission?.currentRevisionId ?? "none"}`} revisionId={mission?.currentRevisionId} sessionId={session.sessionId} labels={labels} onValidateSession={validateSession} />
      <SystemPanel data={data} mission={mission} session={session} labels={labels} readOnly={readOnly} client={client} run={run} signedExport={signedExport} onSignedExport={(value) => setScope((current) => ({ ...current, signedExport: value }))} />
    </main></div>;
}

function LoginScreen({ client, connection, labels, lockState, message, locale, onLocale, onLogin, onRetryLock }: { client: EdgeApiClient; connection: ConnectionState; labels: Labels; lockState: LockState; message: string; locale: Locale; onLocale(): void; onLogin(session: AuthenticatedSession): Promise<void>; onRetryLock(): void }): JSX.Element {
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string>();
  const submit = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); if (lockState !== "idle") return; setBusy(true); setError(undefined); const form = new FormData(event.currentTarget); try { await onLogin(await client.login(String(form.get("userId") ?? ""), String(form.get("password") ?? ""))); } catch (reason) { setError(reason instanceof EdgeApiError ? errorLabel(labels, reason.code) : labels.edgeDisconnected); } finally { setBusy(false); } };
  return <main className="login-screen theme-night"><Brand labels={labels} /><form className="login-card" onSubmit={(event) => void submit(event)}><span className="section-kicker">fac-isr-sms@0.2.0-rc.1</span><h1>{labels.signInTitle}</h1><Status state={connection}>{message}</Status><label>{labels.userId}<input autoComplete="username" disabled={lockState !== "idle"} name="userId" required /></label><label>{labels.password}<input autoComplete="current-password" disabled={lockState !== "idle"} name="password" required type="password" /></label>{error === undefined ? null : <p className="form-error" role="alert">{error}</p>}<button disabled={busy || lockState !== "idle"} type="submit">{busy ? labels.signingIn : labels.signIn}</button>{lockState === "unconfirmed" ? <button onClick={onRetryLock} type="button">{labels.retryLock}</button> : null}<button onClick={onLocale} type="button">{locale === "en" ? labels.spanish : labels.english}</button></form></main>;
}

function JsonAlert({ message }: { message: string }): JSX.Element { return <p aria-label={message} className="form-error" ref={(node) => { node?.focus(); }} role="alert" tabIndex={-1}>{message}</p>; }
function MissionCreator({ canManage, labels, readOnly, client, run }: { canManage: boolean; labels: Labels; readOnly: boolean; client: EdgeApiClient; run: RunOperation }): JSX.Element | null {
  const [error, setError] = useState(false); if (!canManage) return null;
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); if (readOnly) return; const value = String(new FormData(event.currentTarget).get("mission") ?? ""); try { const body = JSON.parse(value) as unknown; setError(false); void run((signal) => client.post("/api/missions", body, signal), { key: "missionCreated" }); } catch { setError(true); } };
  return <details><summary>{labels.createMission}</summary><form className="inline-form" onSubmit={submit}><label>{labels.missionJson}<textarea name="mission" required /></label>{error ? <JsonAlert message={labels.missionJsonInvalid} /> : null}<button disabled={readOnly} type="submit">{labels.createMission}</button>{readOnly ? <StateBlock labels={labels} state="blocked" detail={labels.readOnlyBlocked} /> : null}</form></details>;
}
function MissionRevision({ mission, canManage, labels, readOnly, client, run }: { mission?: MissionView; canManage: boolean; labels: Labels; readOnly: boolean; client: EdgeApiClient; run: RunOperation }): JSX.Element {
  const [error, setError] = useState(false); const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); if (mission === undefined || readOnly) return; const value = String(new FormData(event.currentTarget).get("revision") ?? ""); try { const body = JSON.parse(value) as unknown; setError(false); void run((signal) => client.post(`/api/missions/${encodeURIComponent(mission.missionId)}/revisions`, body, signal), { key: "revisionRecorded" }); } catch { setError(true); } };
  if (mission === undefined) return <article className="ops-card"><h2>{labels.currentRevision}</h2><StateBlock labels={labels} state="blocked" detail={labels.selectMission} /></article>;
  const revision = mission.currentRevision;
  return <article className="ops-card"><h2>{labels.currentRevision}</h2><dl className="facts"><Fact label={labels.id} value={revision.id} /><Fact label={labels.revision} value={String(revision.revision)} /><Fact label={labels.state} value={operatorLabel(labels, revision.state)} /><Fact label={labels.configuration} value={revision.configuration ?? labels.notProvided} /></dl>{canManage ? <details><summary>{labels.createMaterialRevision}</summary><form className="inline-form" onSubmit={submit}><label>{labels.revisionChangeJson}<textarea name="revision" required /></label>{error ? <JsonAlert message={labels.revisionJsonInvalid} /> : null}<button disabled={readOnly} type="submit">{labels.submitRevision}</button>{readOnly ? <StateBlock labels={labels} state="blocked" detail={labels.readOnlyBlocked} /> : null}</form></details> : <StateBlock labels={labels} state="forbidden" detail={labels.revisionForbidden} />}</article>;
}

function Checklist({ mission, labels, readOnly, client, run }: { mission?: MissionView; labels: Labels; readOnly: boolean; client: EdgeApiClient; run: RunOperation }): JSX.Element {
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); if (mission === undefined || readOnly) return; const form = new FormData(event.currentTarget); const itemId = String(form.get("itemId")); void run((signal) => client.post(`/api/revisions/${encodeURIComponent(mission.currentRevisionId)}/checklist-responses`, { responseId: `${mission.currentRevisionId}:${itemId}`, itemId, response: String(form.get("response")), reason: String(form.get("reason")), expectedRevisionId: mission.currentRevisionId }, signal), { key: "checklistRecorded" }); };
  const responses = mission?.checklistResponses.filter(({ revisionId }) => revisionId === mission.currentRevisionId) ?? [];
  return <section className="ops-card" id="checklists" aria-labelledby="checklist-heading"><h2 id="checklist-heading">{labels.itemizedChecklist}</h2>{responses.length === 0 ? <StateBlock labels={labels} state="blocked" detail={labels.noChecklist} /> : <ul className="record-list">{responses.map((item) => <li key={item.responseId}><strong>{item.itemId}</strong><span>{operatorLabel(labels, item.response)} · {item.actorUserId} · {item.occurredAtUtc}</span></li>)}</ul>}<form className="inline-form columns" onSubmit={submit}><label>{labels.itemId}<input name="itemId" required /></label><label>{labels.response}<select name="response"><option value="pass">{labels.responsePass}</option><option value="block">{labels.responseBlock}</option><option value="not-applicable">{labels.responseNotApplicable}</option></select></label><label>{labels.reason}<input name="reason" required /></label><button disabled={readOnly || mission === undefined || responses.length >= 128} type="submit">{labels.respondItem}</button>{readOnly ? <StateBlock labels={labels} state="blocked" detail={labels.readOnlyBlocked} /> : null}</form></section>;
}

function GateGrid({ mission, session, blocked, labels, readOnly, client, run }: { mission?: MissionView; session: AuthenticatedSession; blocked: boolean; labels: Labels; readOnly: boolean; client: EdgeApiClient; run: RunOperation }): JSX.Element {
  const responses = mission?.checklistResponses.filter(({ revisionId }) => revisionId === mission.currentRevisionId) ?? [];
  return <section className="gate-section" id="gates" aria-labelledby="gates-heading"><h2 id="gates-heading">{labels.fourGates}</h2>{readOnly ? <StateBlock labels={labels} state="blocked" detail={labels.readOnlyBlocked} /> : null}<div className="live-gates">{GATES.map((gate, index) => { const approval = mission?.gateApprovals.find((item) => item.missionRevisionId === mission.currentRevisionId && item.gate === gate); const required = ROLE_FOR_GATE[gate]; const allowed = required === "safety" ? session.roles.includes("safety-officer") : session.roles.includes(required);
    const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); if (mission === undefined || readOnly) return; const form = new FormData(event.currentTarget); const aircraftId = gate === "operator" ? mission.currentRevision.aircraft?.[0]?.aircraftId : undefined; void run((signal) => client.post(`/api/revisions/${encodeURIComponent(mission.currentRevisionId)}/gates/${gate}`, { decision: String(form.get("decision")), reason: String(form.get("reason")), evidenceSnapshotId: String(mission.currentRevision.evidenceSnapshotId ?? ""), checklistResponseIds: responses.map(({ responseId }) => responseId), expectedRevisionId: mission.currentRevisionId, ...(aircraftId === undefined ? {} : { aircraftId }) }, signal), { text: labels.gateRecorded.replace("{gate}", operatorLabel(labels, gate)) }); };
    const gateLabel = operatorLabel(labels, gate); const requiredLabel = operatorLabel(labels, required);
    return <article className="ops-card gate-live" key={gate}><span>{labels.gate} 0{index + 1}</span><h3>{gateLabel}</h3><Status state={approval === undefined ? "blocked" : approval.decision === "accept" ? "api-ready" : "blocked"}>{approval === undefined ? labels.pending : operatorLabel(labels, approval.decision)}</Status><p>{labels.requiredRole}: {requiredLabel}</p>{allowed ? <form className="inline-form" onSubmit={submit}><label>{labels.decision}<select name="decision"><option value="accept" disabled={blocked}>{labels.accept}</option><option value="block">{labels.block}</option><option value="escalate">{labels.escalate}</option></select></label><label>{labels.reason}<input name="reason" required /></label><button disabled={readOnly || mission === undefined || responses.length === 0 || approval !== undefined || session.requiresReauthentication} type="submit">{labels.recordGate}</button></form> : <StateBlock labels={labels} state="forbidden" detail={labels.onlyAssigned.replace("{role}", requiredLabel)} />}{session.requiresReauthentication && allowed ? <StateBlock labels={labels} state="blocked" detail={labels.reauthenticationRequired} /> : null}</article>; })}</div></section>;
}

const TelemetryBoundary = memo(function TelemetryBoundary({ revisionId, sessionId, labels, onValidateSession }: { revisionId?: string; sessionId: string; labels: Labels; onValidateSession(): Promise<void> }): JSX.Element {
  const [records, setRecords] = useState<readonly TelemetryRecord[]>([]); const [state, setState] = useState<"loading" | "connected" | "disconnected">("disconnected"); const validating = useRef(false);
  useEffect(() => {
    setRecords([]); if (revisionId === undefined || typeof EventSource === "undefined") { setState("disconnected"); return; }
    let active = true; setState("loading"); const source = new EventSource(`/api/revisions/${encodeURIComponent(revisionId)}/telemetry/stream?window=50&follow=true`);
    source.onopen = () => { if (active) setState("connected"); };
    source.onmessage = ({ data: payload }) => { if (!active) return; try { const record = JSON.parse(payload) as TelemetryRecord; if (record.revisionId === revisionId) setRecords((current) => [...current.slice(-49), record]); } catch { setState("disconnected"); } };
    source.onerror = () => { if (!active) return; setState("disconnected"); if (!validating.current) { validating.current = true; void onValidateSession().finally(() => { validating.current = false; }); } };
    return () => { active = false; source.close(); };
  }, [onValidateSession, revisionId, sessionId]);
  const latest = records.at(-1); const stateLabel = state === "loading" ? labels.loading : state === "connected" ? labels.connected : labels.disconnected;
  return <section className="ops-card" id="telemetry" aria-labelledby="telemetry-heading"><div className="card-heading"><h2 id="telemetry-heading">{labels.readOnlyTelemetry}</h2><Status state={state}>{stateLabel}</Status></div>{latest === undefined ? <StateBlock labels={labels} state={state} detail={labels.noTelemetry} /> : <><p>{String(latest.event.observedAtUtc ?? labels.apiTimeMissing)} · {labels.sequence} {latest.sequence}</p><pre tabIndex={0}>{JSON.stringify(latest.event, null, 2)}</pre></>}</section>;
});

function SystemPanel({ data, mission, session, labels, readOnly, client, run, signedExport, onSignedExport }: { data?: OperationalData; mission?: MissionView; session: AuthenticatedSession; labels: Labels; readOnly: boolean; client: EdgeApiClient; run: RunOperation; signedExport?: SignedMissionExport; onSignedExport(value: SignedMissionExport): void }): JSX.Element {
  const [password, setPassword] = useState(""); const canReauthenticate = session.roles.some((role) => GATE_ROLES.includes(role)); const canExport = session.roles.some((role) => role === "commander" || role === "reviewer");
  const reauth = () => void run(async (signal) => { await client.reauthenticate(password, signal); setPassword(""); }, { key: "reauthenticated" }); const exportMission = () => { if (mission !== undefined) void run(async (signal) => onSignedExport(await client.post<SignedMissionExport>(`/api/revisions/${encodeURIComponent(mission.currentRevisionId)}/export`, undefined, signal)), { key: "signedExportReceived" }); };
  return <section className="system-grid" id="system" aria-labelledby="system-heading"><h2 id="system-heading">{labels.systemHeading}</h2><article className="ops-card"><h3>{labels.packages}</h3>{data?.packages.active.length ? data.packages.active.map((item) => <p key={`${item.packageId}:${item.version}`}><strong>{item.packageId}</strong> {item.version} · {labels.apiState}: {operatorLabel(labels, item.state)}</p>) : <StateBlock labels={labels} state="blocked" detail={labels.noActivePackage} />}{data?.packages.quarantined.length ? <Status state="blocked">{data.packages.quarantined.length} {labels.quarantined}</Status> : null}</article><article className="ops-card"><h3>{labels.readiness}</h3><Status state={data?.readiness.technicalReady ? "api-ready" : "blocked"}>{labels.technical}: {data?.readiness.technicalReady ? labels.ready : labels.notReady}</Status><Status state="blocked">{labels.operational}: {labels.notReady}</Status>{data === undefined ? null : <ul>{Object.entries(data.readiness.checks).map(([name, check]) => <li key={name}>{displayCheck(labels, name)}: {operatorLabel(labels, check.status)}{readinessDetail(labels, check.detail)}</li>)}</ul>}</article><article className="ops-card"><h3>{labels.auditHealth}</h3>{data === undefined ? <StateBlock labels={labels} state="loading" /> : <div data-testid="audit-facts"><Status state={data.audit.state === "healthy" ? "api-ready" : "safe-mode"}>{operatorLabel(labels, data.audit.state)}</Status><p>{data.audit.eventCount} {labels.events}</p>{data.audit.lastEventHash ? <code>{data.audit.lastEventHash}</code> : null}</div>}</article><article className="ops-card"><h3>{labels.signedExport}</h3>{canReauthenticate ? <><label>{labels.reauthPassword}<input onChange={(event) => setPassword(event.target.value)} type="password" value={password} /></label><button disabled={readOnly || password === ""} onClick={reauth} type="button">{labels.reauthenticate}</button></> : null}{canExport ? <button disabled={readOnly || mission === undefined || session.requiresReauthentication} onClick={exportMission} type="button">{labels.requestSignedExport}</button> : <StateBlock labels={labels} state="forbidden" detail={labels.exportRoleRequired} />}{readOnly ? <StateBlock labels={labels} state="blocked" detail={labels.readOnlyBlocked} /> : null}{signedExport === undefined ? null : <dl className="facts"><Fact label={labels.export} value={signedExport.exportId} /><Fact label={labels.key} value={signedExport.signatureKeyId} /><Fact label={labels.algorithm} value={signedExport.signatureAlgorithm} /><Fact label={labels.signature} value={signedExport.detachedSignature} /></dl>}</article></section>;
}

function Brand({ labels }: { labels: Labels }): JSX.Element { return <div className="brand-lockup"><span className="brand-mark" aria-hidden="true">✦</span><div><strong>FAC ISR SMS</strong><span>{labels.operationalCore} · 0.2.0-rc.1</span></div></div>; }
function Fact({ label, value }: { label: string; value: string }): JSX.Element { return <div><dt>{label}</dt><dd>{value}</dd></div>; }
function Status({ state, children }: { state: string; children: ReactNode }): JSX.Element { return <span className={`live-status state-${state}`} role="status">{children}</span>; }
function StateBlock({ labels, state, detail }: { labels: Labels; state: string; detail?: string }): JSX.Element { const translated = state === "loading" ? labels.loading : state === "connected" ? labels.connected : state === "disconnected" ? labels.disconnected : state === "safe-mode" ? labels.safeMode : state === "forbidden" ? labels.forbiddenState : state === "stale" ? labels.stale : labels.blockedState; return <div className={`state-block state-${state}`} role="status"><strong>{translated}</strong>{detail ? <span>{detail}</span> : null}</div>; }
