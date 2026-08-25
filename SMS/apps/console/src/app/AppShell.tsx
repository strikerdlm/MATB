import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent, JSX, ReactNode } from "react";
import { EdgeApiClient, EdgeApiError, SessionExpiredError } from "../api/client.js";
import type { AuditHealth, AuthenticatedSession, MissionList, MissionView, PackageList, ReadinessReport, SignedMissionExport, TelemetryRecord, UserRole } from "../api/types.js";
import { getLabels, type Locale } from "../i18n/registry.js";

export interface AppShellProps { readonly initialPath?: string; readonly initialLocale?: Locale; readonly apiClient?: EdgeApiClient }
type ConnectionState = "loading" | "connected" | "disconnected" | "forbidden" | "safe-mode";
type GateName = "maintenance" | "operator" | "safety" | "commander";
const GATES: readonly GateName[] = ["maintenance", "operator", "safety", "commander"];
const ROLE_FOR_GATE: Readonly<Record<GateName, UserRole | "safety">> = { maintenance: "maintainer", operator: "operator", safety: "safety", commander: "commander" };
const DEFERRED = ["Fleet", "Planning", "Assurance", "Research", "Reports", "Documents", "Notes"] as const;
interface OperationalData { readonly missions: MissionList; readonly packages: PackageList; readonly readiness: ReadinessReport; readonly audit: AuditHealth }

export function AppShell({ initialLocale = "en", apiClient }: AppShellProps): JSX.Element {
  const client = useMemo(() => apiClient ?? new EdgeApiClient(), [apiClient]);
  const [locale, setLocale] = useState<Locale>(initialLocale);
  const [night, setNight] = useState(true);
  const [session, setSession] = useState<AuthenticatedSession>();
  const [connection, setConnection] = useState<ConnectionState>("disconnected");
  const [message, setMessage] = useState("Sign in to operational console");
  const [data, setData] = useState<OperationalData>();
  const [selectedMissionId, setSelectedMissionId] = useState<string>();
  const [telemetry, setTelemetry] = useState<readonly TelemetryRecord[]>([]);
  const [telemetryState, setTelemetryState] = useState<"loading" | "connected" | "disconnected">("disconnected");
  const [signedExport, setSignedExport] = useState<SignedMissionExport>();
  const labels = getLabels(locale);
  const mission = data?.missions.missions.find(({ missionId }) => missionId === selectedMissionId) ?? data?.missions.missions[0];

  const clearSession = useCallback((error: unknown) => {
    setSession(undefined); setData(undefined); setTelemetry([]); setConnection("disconnected");
    setMessage(error instanceof SessionExpiredError ? "Session expired — sign in again" : error instanceof Error ? error.message : "Edge API disconnected");
  }, []);
  const loadData = useCallback(async (active: AuthenticatedSession) => {
    setConnection("loading"); setMessage("Loading authoritative operational state");
    try {
      const [missions, packages, readiness, audit] = await Promise.all([
        client.get<MissionList>("/api/missions"), client.get<PackageList>("/api/packages"),
        client.readiness(), client.get<AuditHealth>("/api/audit/health"),
      ]);
      setSession(active); setData({ missions, packages, readiness, audit });
      setSelectedMissionId((current) => current ?? missions.missions[0]?.missionId);
      const safeMode = audit.state === "safe-mode" || Object.values(readiness.checks).some(({ detail }) => detail?.includes("read-only"));
      setConnection(safeMode ? "safe-mode" : "connected"); setMessage(safeMode ? "Read-only safe mode" : "Connected to Edge API");
    } catch (error) {
      if (error instanceof EdgeApiError && error.status === 403) { setConnection("forbidden"); setMessage("Forbidden for this role"); return; }
      clearSession(error);
    }
  }, [client, clearSession]);

  useEffect(() => {
    const revisionId = mission?.currentRevisionId;
    if (session === undefined || revisionId === undefined || typeof EventSource === "undefined") return;
    setTelemetryState("loading");
    const source = new EventSource(`/api/revisions/${encodeURIComponent(revisionId)}/telemetry/stream?window=50&follow=true`);
    source.onopen = () => setTelemetryState("connected");
    source.onmessage = ({ data: payload }) => {
      try { setTelemetry((records) => [...records.slice(-49), JSON.parse(payload) as TelemetryRecord]); } catch { setTelemetryState("disconnected"); }
    };
    source.onerror = () => setTelemetryState("disconnected");
    return () => source.close();
  }, [mission?.currentRevisionId, session?.sessionId]);

  const run = useCallback(async (operation: () => Promise<unknown>, success: string) => {
    try { await operation(); setMessage(success); const active = client.session(); if (active !== undefined) await loadData(active); }
    catch (error) {
      if (error instanceof SessionExpiredError) clearSession(error);
      else if (error instanceof EdgeApiError && error.status === 403) { setConnection("forbidden"); setMessage(`Forbidden: ${error.message}`); }
      else setMessage(error instanceof Error ? error.message : "Request failed");
    }
  }, [client, clearSession, loadData]);

  if (session === undefined) return <LoginScreen client={client} connection={connection} message={message} locale={locale} onLocale={() => setLocale(locale === "en" ? "es" : "en")} onLogin={(next) => void loadData(next)} />;
  const safety = mission?.safetyResults.find(({ revisionId }) => revisionId === mission.currentRevisionId);
  const stale = safety?.stale === true;
  const blocked = safety === undefined || stale || safety.status !== "ready";
  return <div className={`console-shell live-console ${night ? "theme-night" : "theme-day"}`}>
    <aside className="side-rail" aria-label="Primary navigation"><Brand /><nav aria-label="Mission navigation" className="live-nav">
      <a href="#mission">{labels.overview}</a><a href="#safety">{labels.safetyReview}</a><a href="#checklists">Checklist</a><a href="#gates">Gates</a><a href="#telemetry">{labels.telemetry}</a><a href="#system">System</a>
    </nav><div className="deferred-list" aria-label="Deferred modules" tabIndex={0}>{DEFERRED.map((name) => <button disabled key={name} type="button"><span>{name}</span><small>Not included in 0.2.0-rc.1</small></button>)}</div></aside>
    <main className="main-frame live-main"><header className="top-bar live-topbar"><div><strong>{session.userId}</strong><span>{session.roles.join(" · ")}</span></div><div className="top-controls"><Status state={connection}>{message}</Status>
      <button aria-label="Change language" className="locale-toggle" onClick={() => setLocale(locale === "en" ? "es" : "en")} type="button">{locale.toUpperCase()} / {locale === "en" ? "ES" : "EN"}</button>
      <button aria-label="Toggle day and night theme" className="theme-toggle" onClick={() => setNight((value) => !value)} type="button">{night ? "Day" : "Night"}</button>
      <button onClick={() => void client.lock().finally(() => { setSession(undefined); setData(undefined); setMessage("Locked"); })} type="button">Lock</button></div></header>
      <div className="classification-banner">{labels.unclassified}</div>
      <section className="live-grid" id="mission" aria-labelledby="missions-heading"><article className="ops-card mission-list"><h1 id="missions-heading">Missions</h1>{data === undefined ? <StateBlock state="loading" /> : data.missions.missions.length === 0 ? <StateBlock state="blocked" detail="No assigned missions" /> : data.missions.missions.map((item) => <button className={item.missionId === mission?.missionId ? "selected" : ""} key={item.missionId} onClick={() => setSelectedMissionId(item.missionId)} type="button"><strong>{item.missionId}</strong><span>Revision {item.currentRevision.revision} · {item.currentRevision.state}</span></button>)}</article>
        <MissionRevision mission={mission} canManage={session.roles.some((role) => role === "commander" || role === "safety-officer")} client={client} run={run} /></section>
      <section className={`ops-card safety-card state-${stale ? "stale" : blocked ? "blocked" : "api-ready"}`} id="safety" aria-labelledby="safety-heading"><div className="card-heading"><div><span>Server-owned evaluation</span><h2 id="safety-heading">{labels.missionStrip}</h2></div><Status state={stale ? "stale" : blocked ? "blocked" : "api-ready"}>{stale ? "Stale" : safety?.status ?? "Unavailable"}</Status></div>
        {safety === undefined ? <StateBlock state="safe-mode" detail="Safety evaluation unavailable — approvals remain blocked" /> : <><dl className="facts"><Fact label="Revision" value={safety.revisionId} /><Fact label="Evaluated" value={safety.evaluatedAtUtc ?? "API did not provide time"} /><Fact label="Status" value={safety.status} /></dl>{safety.blockers.length === 0 ? <p>The API reports no safety blockers for this revision.</p> : <ul>{safety.blockers.map((item, index) => <li key={`${item.code}-${index}`}><strong>{item.code}</strong> {item.explanation ?? "Server blocker"}</li>)}</ul>}</>}
      </section>
      <Checklist mission={mission} client={client} run={run} /><GateGrid mission={mission} session={session} blocked={blocked} client={client} run={run} /><Telemetry records={telemetry} state={telemetryState} />
      <SystemPanel data={data} mission={mission} session={session} client={client} run={run} signedExport={signedExport} setSignedExport={setSignedExport} />
    </main></div>;
}

function LoginScreen({ client, connection, message, locale, onLocale, onLogin }: { client: EdgeApiClient; connection: ConnectionState; message: string; locale: Locale; onLocale(): void; onLogin(session: AuthenticatedSession): void }): JSX.Element {
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string>();
  const submit = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); setBusy(true); setError(undefined); const form = new FormData(event.currentTarget); try { onLogin(await client.login(String(form.get("userId") ?? ""), String(form.get("password") ?? ""))); } catch (reason) { setError(reason instanceof Error ? reason.message : "Sign-in failed"); setBusy(false); } };
  return <main className="login-screen theme-night"><Brand /><form className="login-card" onSubmit={(event) => void submit(event)}><span className="section-kicker">fac-isr-sms@0.2.0-rc.1</span><h1>Sign in to operational console</h1><Status state={connection}>{message}</Status><label>User ID<input autoComplete="username" name="userId" required /></label><label>Password<input autoComplete="current-password" name="password" required type="password" /></label>{error === undefined ? null : <p className="form-error" role="alert">{error}</p>}<button disabled={busy} type="submit">{busy ? "Signing in…" : "Sign in"}</button><button onClick={onLocale} type="button">{locale === "en" ? "Español" : "English"}</button></form></main>;
}

function MissionRevision({ mission, canManage, client, run }: { mission?: MissionView; canManage: boolean; client: EdgeApiClient; run(operation: () => Promise<unknown>, success: string): Promise<void> | void }): JSX.Element {
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); if (mission === undefined) return; const value = String(new FormData(event.currentTarget).get("revision") ?? ""); try { const body = JSON.parse(value) as unknown; void run(() => client.post(`/api/missions/${encodeURIComponent(mission.missionId)}/revisions`, body), "Revision recorded"); } catch { /* browser validation message below remains explicit */ } };
  if (mission === undefined) return <article className="ops-card"><h2>Current revision</h2><StateBlock state="blocked" detail="Select an assigned mission" /></article>;
  const revision = mission.currentRevision;
  return <article className="ops-card"><h2>Current revision</h2><dl className="facts"><Fact label="ID" value={revision.id} /><Fact label="Revision" value={String(revision.revision)} /><Fact label="State" value={revision.state} /><Fact label="Configuration" value={revision.configuration ?? "Not provided"} /></dl>{canManage ? <details><summary>Create material revision</summary><form className="inline-form" onSubmit={submit}><label>Revision change JSON<textarea name="revision" required /></label><button type="submit">Submit revision</button></form></details> : <StateBlock state="forbidden" detail="Commander or safety-officer role required to revise" />}</article>;
}

function Checklist({ mission, client, run }: { mission?: MissionView; client: EdgeApiClient; run(operation: () => Promise<unknown>, success: string): Promise<void> | void }): JSX.Element {
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); if (mission === undefined) return; const form = new FormData(event.currentTarget); const itemId = String(form.get("itemId")); void run(() => client.post(`/api/revisions/${encodeURIComponent(mission.currentRevisionId)}/checklist-responses`, { responseId: `${mission.currentRevisionId}:${itemId}`, itemId, response: String(form.get("response")), reason: String(form.get("reason")), expectedRevisionId: mission.currentRevisionId }), "Checklist item recorded"); };
  const responses = mission?.checklistResponses.filter(({ revisionId }) => revisionId === mission.currentRevisionId) ?? [];
  return <section className="ops-card" id="checklists" aria-labelledby="checklist-heading"><h2 id="checklist-heading">Itemized checklist</h2>{responses.length === 0 ? <StateBlock state="blocked" detail="No checklist responses recorded for this revision" /> : <ul className="record-list">{responses.map((item) => <li key={item.responseId}><strong>{item.itemId}</strong><span>{item.response} · {item.actorUserId} · {item.occurredAtUtc}</span></li>)}</ul>}<form className="inline-form columns" onSubmit={submit}><label>Item ID<input name="itemId" required /></label><label>Response<select name="response"><option value="pass">Pass</option><option value="block">Block</option><option value="not-applicable">Not applicable</option></select></label><label>Reason<input name="reason" required /></label><button disabled={mission === undefined || responses.length >= 128} type="submit">Respond to item</button></form></section>;
}

function GateGrid({ mission, session, blocked, client, run }: { mission?: MissionView; session: AuthenticatedSession; blocked: boolean; client: EdgeApiClient; run(operation: () => Promise<unknown>, success: string): Promise<void> | void }): JSX.Element {
  const responses = mission?.checklistResponses.filter(({ revisionId }) => revisionId === mission.currentRevisionId) ?? [];
  return <section className="gate-section" id="gates" aria-labelledby="gates-heading"><h2 id="gates-heading">Four role-separated gates</h2><div className="live-gates">{GATES.map((gate, index) => { const approval = mission?.gateApprovals.find((item) => item.missionRevisionId === mission.currentRevisionId && item.gate === gate); const required = ROLE_FOR_GATE[gate]; const allowed = required === "safety" ? session.roles.includes("safety-officer") : session.roles.includes(required);
    const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); if (mission === undefined) return; const form = new FormData(event.currentTarget); const aircraftId = gate === "operator" ? mission.currentRevision.aircraft?.[0]?.aircraftId : undefined; void run(() => client.post(`/api/revisions/${encodeURIComponent(mission.currentRevisionId)}/gates/${gate}`, { decision: String(form.get("decision")), reason: String(form.get("reason")), evidenceSnapshotId: String(mission.currentRevision.evidenceSnapshotId ?? ""), checklistResponseIds: responses.map(({ responseId }) => responseId), expectedRevisionId: mission.currentRevisionId, ...(aircraftId === undefined ? {} : { aircraftId }) }), `${gate} gate recorded`); };
    return <article className="ops-card gate-live" key={gate}><span>Gate 0{index + 1}</span><h3>{gate}</h3><Status state={approval === undefined ? "blocked" : approval.decision === "accept" ? "api-ready" : "blocked"}>{approval?.decision ?? "Pending"}</Status><p>Required role: {required}</p>{allowed ? <form className="inline-form" onSubmit={submit}><label>Decision<select name="decision"><option value="accept" disabled={blocked}>Accept</option><option value="block">Block</option><option value="escalate">Escalate</option></select></label><label>Reason<input name="reason" required /></label><button disabled={mission === undefined || responses.length === 0 || approval !== undefined || session.requiresReauthentication} type="submit">Record gate</button></form> : <StateBlock state="forbidden" detail={`Only assigned ${required} may decide`} />}{session.requiresReauthentication && allowed ? <StateBlock state="blocked" detail="Re-authentication required" /> : null}</article>; })}</div></section>;
}

function Telemetry({ records, state }: { records: readonly TelemetryRecord[]; state: "loading" | "connected" | "disconnected" }): JSX.Element { const latest = records.at(-1); return <section className="ops-card" id="telemetry" aria-labelledby="telemetry-heading"><div className="card-heading"><h2 id="telemetry-heading">Read-only telemetry</h2><Status state={state}>{state}</Status></div>{latest === undefined ? <StateBlock state={state} detail="No authorized telemetry records received" /> : <><p>{String(latest.event.observedAtUtc ?? "API time unavailable")} · sequence {latest.sequence}</p><pre tabIndex={0}>{JSON.stringify(latest.event, null, 2)}</pre></>}</section>; }

function SystemPanel({ data, mission, session, client, run, signedExport, setSignedExport }: { data?: OperationalData; mission?: MissionView; session: AuthenticatedSession; client: EdgeApiClient; run(operation: () => Promise<unknown>, success: string): Promise<void> | void; signedExport?: SignedMissionExport; setSignedExport(value: SignedMissionExport): void }): JSX.Element {
  const [password, setPassword] = useState(""); const reauth = () => void run(async () => { await client.reauthenticate(password); setPassword(""); }, "Re-authenticated"); const exportMission = () => { if (mission !== undefined) void run(async () => setSignedExport(await client.post<SignedMissionExport>(`/api/revisions/${encodeURIComponent(mission.currentRevisionId)}/export`)), "Signed export received"); };
  return <section className="system-grid" id="system" aria-labelledby="system-heading"><h2 id="system-heading">Package, readiness, audit and export</h2><article className="ops-card"><h3>Packages</h3>{data?.packages.active.length ? data.packages.active.map((item) => <p key={`${item.packageId}:${item.version}`}><strong>{item.packageId}</strong> {item.version} · API state: {item.state}</p>) : <StateBlock state="blocked" detail="No active package reported" />}{data?.packages.quarantined.length ? <Status state="blocked">{data.packages.quarantined.length} quarantined</Status> : null}</article><article className="ops-card"><h3>Readiness</h3><Status state={data?.readiness.technicalReady ? "api-ready" : "blocked"}>Technical: {data?.readiness.technicalReady ? "ready" : "not ready"}</Status><Status state="blocked">Operational: false</Status>{data === undefined ? null : <ul>{Object.entries(data.readiness.checks).map(([name, check]) => <li key={name}>{name}: {check.status}{check.detail ? ` — ${check.detail}` : ""}</li>)}</ul>}</article><article className="ops-card"><h3>Audit health</h3>{data === undefined ? <StateBlock state="loading" /> : <><Status state={data.audit.state === "healthy" ? "api-ready" : "safe-mode"}>{data.audit.state}</Status><p>{data.audit.eventCount} events</p>{data.audit.lastEventHash ? <code>{data.audit.lastEventHash}</code> : null}</>}</article><article className="ops-card"><h3>Signed export</h3>{session.roles.some((role) => role === "commander" || role === "reviewer") ? <><label>Re-authentication password<input onChange={(event) => setPassword(event.target.value)} type="password" value={password} /></label><button disabled={password === ""} onClick={reauth} type="button">Re-authenticate</button><button disabled={mission === undefined || session.requiresReauthentication} onClick={exportMission} type="button">Request signed export</button></> : <StateBlock state="forbidden" detail="Commander or reviewer role required" />}{signedExport === undefined ? null : <dl className="facts"><Fact label="Export" value={signedExport.exportId} /><Fact label="Key" value={signedExport.signatureKeyId} /><Fact label="Algorithm" value={signedExport.signatureAlgorithm} /><Fact label="Signature" value={signedExport.detachedSignature} /></dl>}</article></section>;
}

function Brand(): JSX.Element { return <div className="brand-lockup"><span className="brand-mark" aria-hidden="true">✦</span><div><strong>FAC ISR SMS</strong><span>Operational core · 0.2.0-rc.1</span></div></div>; }
function Fact({ label, value }: { label: string; value: string }): JSX.Element { return <div><dt>{label}</dt><dd>{value}</dd></div>; }
function Status({ state, children }: { state: string; children: ReactNode }): JSX.Element { return <span className={`live-status state-${state}`} role="status">{children}</span>; }
function StateBlock({ state, detail }: { state: string; detail?: string }): JSX.Element { return <div className={`state-block state-${state}`} role="status"><strong>{state}</strong>{detail ? <span>{detail}</span> : null}</div>; }
