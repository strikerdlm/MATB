# sUAS C2 Phase 4 — Operator UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a bilingual browser workflow that prepares a session and lets one operator supervise 2–8 synthetic sUAS through an offline tactical console.

**Architecture:** Typed API/WebSocket adapters feed a dedicated Zustand simulation store. A full-bleed `/mission` route renders a dependency-free React SVG map plus focused fleet, command, alert, and contact panels; the existing research-console shell remains unchanged on all other routes.

**Tech Stack:** Next.js 14.2+, React 18.2+, TypeScript 5.3+, Zustand 4.5+, TailwindCSS, Radix UI, Lucide React, React SVG, Vitest 2.1+, jsdom, Testing Library.

## Global Constraints

- Complete and push Phases 1–3 first.
- Read the approved design and master interface ledger before editing.
- The UI never advances simulation truth, predicts sensor outcomes, decrements energy, or infers hidden contact truth.
- Use only bundled SVG/CSS/assets; do not add a map/tile/network dependency.
- Store the controller lease only in `sessionStorage`; never render, log, persist in Zustand, or include it in screenshots.
- English and es-CO dictionaries must have identical keys; session locale freezes after preparation.
- Mission state and transport state are separate; a reconnect or animation frame cannot mutate authoritative state.
- Preserve the existing shell and all tracker/participant/upload/visualization/analysis/screen pages.
- Preserve all master-plan accessibility, resolution, offline, test, and Git constraints.

---

### Task 1: Typed simulation contracts, API adapter, localization, and component-test harness

**Files:**
- Modify: `webui/frontend/package.json`
- Modify: `webui/frontend/package-lock.json`
- Modify: `webui/frontend/vitest.config.ts`
- Create: `webui/frontend/src/test/setup.ts`
- Create: `webui/frontend/src/app/api/runtime-config/route.ts`
- Create: `webui/frontend/src/types/simulation.ts`
- Create: `webui/frontend/src/lib/runtime-config.ts`
- Create: `webui/frontend/src/lib/runtime-config.test.ts`
- Modify: `webui/frontend/src/lib/api.ts`
- Create: `webui/frontend/src/lib/simulation/api.ts`
- Create: `webui/frontend/src/lib/simulation/i18n.ts`
- Create: `webui/frontend/src/lib/simulation/api.test.ts`
- Create: `webui/frontend/src/lib/simulation/i18n.test.ts`

**Interfaces:**
- Consumes: Phase 3 REST/JSON contract.
- Produces: runtime local-backend discovery shared by legacy/native clients, all TypeScript types in the master ledger, `simulationApi`, `simulationWsUrl()`, `Locale`, `TranslationKey`, `t()`, and jsdom-enabled component tests.

- [ ] **Step 1: Install the exact UI test dependencies and configure Vitest**

Run from `webui/frontend`:

```bash
npm install --save-dev @testing-library/react@14.3.1 @testing-library/user-event@14.5.2 @testing-library/jest-dom@6.4.8 jsdom@24.1.1
```

Set `test.environment="jsdom"`, retain `src/**/*.test.ts` and add `src/**/*.test.tsx`, and load `src/test/setup.ts`. The setup file imports `@testing-library/jest-dom/vitest` and calls `afterEach(cleanup)`.

- [ ] **Step 2: Write failing API and locale-parity tests**

```ts
it("prepares a session and sends the controller header only on mutations", async () => {
  global.fetch = mockFetch(201, preparedSession);
  const prepared = await createSimulationSession({
    participant_id: "P01", visit_ordinal: 1,
    scenario_id: "reference_area_search", locale: "es-CO",
  });
  expect(prepared.controller_lease).toBe("secret");
  global.fetch = mockFetch(200, sessionView);
  await transitionSession(prepared.id, "start", "secret", { block_id: "PRACTICE" });
  const [, init] = (global.fetch as Mock).mock.calls[0];
  expect(new Headers(init.headers).get("X-Simulation-Controller")).toBe("secret");
});

it("converts local HTTP API bases to WebSocket URLs", () => {
  expect(simulationWsUrl("http://127.0.0.1:8000", "sim-1", 20))
    .toBe("ws://127.0.0.1:8000/simulation/sessions/sim-1/stream?after_sequence=20");
});

it("derives the backend origin from browser host and validated runtime port", async () => {
  global.fetch = mockFetch(200, { backend_port: 8123 });
  await expect(getApiBase(new URL("http://lab-host:3100/mission")))
    .resolves.toBe("http://lab-host:8123");
});

it("English and es-CO have identical translation keys", () => {
  expect(Object.keys(STRINGS.en).sort()).toEqual(Object.keys(STRINGS["es-CO"]).sort());
  expect(t("es-CO", "command.return_to_base")).toBe("Regresar a base");
});
```

- [ ] **Step 3: Run tests and confirm missing modules**

Run: `cd webui/frontend && npm test -- --run src/lib/runtime-config.test.ts src/lib/simulation/api.test.ts src/lib/simulation/i18n.test.ts`

Expected: FAIL resolving the new simulation modules.

- [ ] **Step 4: Implement one runtime API-origin source for old and new clients**

`GET /api/runtime-config` is a Next.js route handler that reads server-only `MATB_BACKEND_PORT`, defaults to `8000`, validates integer range `1..65535`, and returns only `{ "backend_port": number }` with `Cache-Control: no-store`. `getApiBase(browserUrl)` fetches that same-origin route once, uses the browser URL's protocol/hostname plus the returned port, and rejects malformed responses. Tests inject the browser URL; product code uses `window.location.href` only inside client-side calls.

Remove the file-scoped `NEXT_PUBLIC_API_URL` constant from existing `src/lib/api.ts`; every existing async API function and the new simulation adapter await the shared cached `getApiBase()`. This preserves old endpoints while allowing the installed frontend build to follow the launcher's backend port without rebuild. WebSocket URL construction converts the same resolved origin to `ws:`/`wss:`. No server address is taken from scenario/query/user content.

- [ ] **Step 5: Define complete transport and world-state types**

In `types/simulation.ts`, define exact unions for locale, lifecycle, profile, aircraft/link/sensor/contact modes, alert severity/kind, command kinds, stream kinds, and connection modes. Define interfaces for `PointMM`, `RouteSnapshot`, `AircraftSnapshot`, `ContactSnapshot` (without `truth`), `AlertSnapshot`, `CoverageSnapshot`, `WorldSnapshot`, `SessionView`, `PreparedSession`, `ScenarioSummary`, `CommandRequest`, `CommandResultView`, `StreamEnvelope`, `ArtifactView`, and `DebriefView`.

The snapshot contract must use ID-keyed records for aircraft/contacts/alerts and sorted arrays for routes/coverage cells. Include `scenario_id`, `block_id`, `tick`, `simulation_time_ms`, `state_version`, `state_sha256`, terrain bounds/polygon, home, initial view, sectors, restricted zones, localized labels/report-note codes, and integer coverage counts/ppm at the root. Do not add future schedule or hidden-truth fields.

- [ ] **Step 6: Implement fetch helpers and stable API errors**

```ts
export class SimulationApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public context?: Record<string, unknown>,
  ) { super(message); this.name = "SimulationApiError"; }
}

async function simulationRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const apiBase = await getApiBase();
  const response = await fetch(`${apiBase}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body.detail ?? body;
    throw new SimulationApiError(response.status, detail.code ?? "unknown_error",
                                 detail.message ?? response.statusText, detail.context);
  }
  return response.json() as Promise<T>;
}
```

Implement `listSimulationScenarios`, `validateSimulationScenario`, `createSimulationSession`, `getSimulationSession`, `transitionSession`, `recoverSimulationSession`, `submitSimulationCommand`, `getSimulationState`, `getSimulationDebrief`, and `listSimulationArtifacts`. Lease-bearing methods set only `X-Simulation-Controller`.

- [ ] **Step 7: Implement complete flat translation dictionaries**

Use `STRINGS.en` as the key source and type `STRINGS["es-CO"]` as `Record<keyof typeof STRINGS.en, string>`. Include setup, lifecycle, connection, fleet fields, every command, every stable backend error, contact states/actions, alert kinds, map layer names, probes, post-block scales, debrief, accessibility labels, and confirmation copy. Do not concatenate translated grammar; use parameter replacement in `t(locale, key, vars)` for `{aircraft}`, `{count}`, `{time}`, and `{block}`.

- [ ] **Step 8: Run focused tests, full frontend unit tests, and typecheck**

```bash
cd webui/frontend
npm test -- --run src/lib/runtime-config.test.ts src/lib/simulation/api.test.ts src/lib/simulation/i18n.test.ts
npm test -- --run
npm run typecheck
```

Expected: PASS.

- [ ] **Step 9: Commit and push Task 1**

```bash
git add webui/frontend/package.json webui/frontend/package-lock.json webui/frontend/vitest.config.ts webui/frontend/src/test/setup.ts webui/frontend/src/app/api/runtime-config/route.ts webui/frontend/src/types/simulation.ts webui/frontend/src/lib/runtime-config.ts webui/frontend/src/lib/runtime-config.test.ts webui/frontend/src/lib/api.ts webui/frontend/src/lib/simulation/api.ts webui/frontend/src/lib/simulation/i18n.ts webui/frontend/src/lib/simulation/api.test.ts webui/frontend/src/lib/simulation/i18n.test.ts
git diff --cached --check
git commit -m "feat(frontend): add typed simulation client"
git push origin HEAD
```

### Task 2: Route-aware shell and researcher mission setup page

**Files:**
- Create: `webui/frontend/src/components/layout/RouteShell.tsx`
- Modify: `webui/frontend/src/app/layout.tsx`
- Modify: `webui/frontend/src/components/layout/SidebarNav.tsx`
- Create: `webui/frontend/src/app/mission/setup/page.tsx`
- Create: `webui/frontend/src/components/mission/setup/MissionSetupForm.tsx`
- Create: `webui/frontend/src/components/mission/setup/MissionSetupForm.test.tsx`

**Interfaces:**
- Consumes: existing participant/visit API, simulation scenario/session API, translations.
- Produces: `/mission/setup`, controller lease session-storage key `matb.simulation.<session-id>.lease`, and full-bleed route switching for live/debrief pages.

- [ ] **Step 1: Write failing setup form behavior tests**

```tsx
it("requires participant visit scenario locale and acknowledgement", async () => {
  render(<MissionSetupForm participants={participants} scenarios={scenarios} />);
  expect(screen.getByRole("button", { name: /prepare session/i })).toBeDisabled();
  await user.selectOptions(screen.getByLabelText(/participant/i), "P01");
  await user.selectOptions(screen.getByLabelText(/visit/i), "1");
  await user.selectOptions(screen.getByLabelText(/scenario/i), "reference_area_search");
  await user.selectOptions(screen.getByLabelText(/language/i), "es-CO");
  await user.click(screen.getByRole("checkbox", { name: /research instrument/i }));
  expect(screen.getByRole("button", { name: /prepare session/i })).toBeEnabled();
});

it("stores the lease in sessionStorage and never renders it", async () => {
  mockCreate.mockResolvedValue(preparedSession);
  render(<MissionSetupForm participants={participants} scenarios={scenarios} />);
  await completeAndSubmit(user);
  expect(sessionStorage.getItem("matb.simulation.sim-1.lease")).toBe("secret");
  expect(document.body).not.toHaveTextContent("secret");
  expect(mockPush).toHaveBeenCalledWith("/mission?session=sim-1");
});
```

- [ ] **Step 2: Run the component test and confirm missing form**

Run: `cd webui/frontend && npm test -- --run src/components/mission/setup/MissionSetupForm.test.tsx`

Expected: FAIL resolving the component.

- [ ] **Step 3: Add the route-aware shell without disturbing existing pages**

`RouteShell` is a client component using `usePathname()`. Render children directly in a `min-h-screen bg-background` container only for exact `/mission` and paths beginning `/mission/debrief`; otherwise render the existing `AppShell`. Change root layout to use `RouteShell`. Add an enabled `Mission` navigation item pointing to `/mission/setup` with a `Radar` icon; keep existing numbering deterministic.

- [ ] **Step 4: Implement setup data loading and strict form state**

The server/client page loads participants and scenarios, then the selected participant's visits. The form has explicit fields, inline loading/error state, manifest summary (hash prefix, fleet range, four profiles, offline status), and acknowledgement. On submit call `createSimulationSession`, store only the lease in session storage, store locale/session ID in URL/session view, clear any older `matb.simulation.*.lease` entries only after confirming they refer to terminal sessions, and navigate to `/mission?session=<encoded-id>`.

The page must display a research-only/non-certified notice and no YAML editor or free-text field.

- [ ] **Step 5: Run setup tests, typecheck, and build**

```bash
cd webui/frontend
npm test -- --run src/components/mission/setup/MissionSetupForm.test.tsx
npm run typecheck
npm run build
```

Expected: PASS; `/mission/setup` appears in build routes.

- [ ] **Step 6: Commit and push Task 2**

```bash
git add webui/frontend/src/components/layout/RouteShell.tsx webui/frontend/src/app/layout.tsx webui/frontend/src/components/layout/SidebarNav.tsx webui/frontend/src/app/mission/setup/page.tsx webui/frontend/src/components/mission/setup/MissionSetupForm.tsx webui/frontend/src/components/mission/setup/MissionSetupForm.test.tsx
git diff --cached --check
git commit -m "feat(frontend): add simulation session setup"
git push origin HEAD
```

### Task 3: WebSocket client, reconnect/gap handling, and simulation store

**Files:**
- Create: `webui/frontend/src/lib/simulation/stream.ts`
- Create: `webui/frontend/src/lib/simulation/store.ts`
- Create: `webui/frontend/src/lib/simulation/interpolation.ts`
- Create: `webui/frontend/src/lib/simulation/stream.test.ts`
- Create: `webui/frontend/src/lib/simulation/store.test.ts`
- Create: `webui/frontend/src/lib/simulation/interpolation.test.ts`

**Interfaces:**
- Consumes: typed stream/state API and session-storage lease.
- Produces: `SimulationStream`, `useSimulationStore`, `applyEnvelope()`, `validCommandsFor()`, `interpolateSnapshot()`.

- [ ] **Step 1: Write failing ordering, gap, reconnect, and interpolation tests**

```ts
it("applies ordered envelopes and fetches truth after a gap", async () => {
  const store = createSimulationStore();
  await store.getState().applyEnvelope(envelope(10, "snapshot", snapshot(10)));
  await store.getState().applyEnvelope(envelope(12, "domain_event", {}));
  expect(store.getState().connection).toBe("reconnecting");
  expect(mockGetState).toHaveBeenCalledWith("sim-1");
  expect(store.getState().lastSequence).toBe(10);
});

it("never applies an older snapshot", () => {
  const store = createSimulationStore();
  store.getState().applyEnvelope(envelope(4, "snapshot", snapshot(8)));
  store.getState().applyEnvelope(envelope(5, "snapshot", snapshot(7)));
  expect(store.getState().snapshot?.state_version).toBe(8);
});

it("interpolates display positions without mutating either snapshot", () => {
  const before = snapshotAt(0, { x_mm: 0, y_mm: 0 });
  const after = snapshotAt(250, { x_mm: 1000, y_mm: 500 });
  const rendered = interpolateSnapshot(before, after, 125);
  expect(rendered.aircraft["UAS-01"].position).toEqual({ x_mm: 500, y_mm: 250 });
  expect(before.aircraft["UAS-01"].position.x_mm).toBe(0);
});
```

- [ ] **Step 2: Run focused tests and confirm missing stream/store**

Run: `cd webui/frontend && npm test -- --run src/lib/simulation/stream.test.ts src/lib/simulation/store.test.ts src/lib/simulation/interpolation.test.ts`

Expected: FAIL resolving the new files.

- [ ] **Step 3: Implement the injectable WebSocket client**

`SimulationStream` receives `webSocketFactory`, timer functions, and callbacks. `connect()` builds the URL from API base/session/last sequence and adds URL-encoded `lease` only for the controller. It parses every message as `StreamEnvelope`, rejects schema-shape failures through `onError`, answers no mission logic, and reconnects after 250, 500, 1,000, then 2,000 ms (2,000 max). Intentional `close()` cancels reconnection. After each open, it waits for the server's full snapshot before marking live. The first snapshot must include `resynchronizes_after_sequence`; the store accepts its fresh transport sequence even if it jumps, replaces REST state, and starts ordinary contiguous-gap enforcement with the following envelope.

- [ ] **Step 4: Implement an isolated Zustand simulation store**

State fields: `session`, `snapshot`, `previousSnapshot`, `lastSequence`, `connection`, `selectedAircraftId`, `selectedContactId`, `pendingCommandIds`, `commandResults`, `transportError`, and `locale`. Actions: `initialize`, async `applyEnvelope`, `replaceAuthoritativeState`, `selectAircraft`, `selectContact`, `submitCommand`, `connect`, `disconnect`, and `reset`.

Rules:

- ignore duplicate sequence; treat a forward gap as reconnecting and fetch REST state;
- ignore snapshots with older state versions;
- lifecycle PAUSED changes connection to paused but retains state;
- never optimistically mutate authoritative aircraft/contact state;
- pending command only affects button busy state until result;
- valid command calculation mirrors backend modes but backend rejection remains final.

- [ ] **Step 5: Implement display-only interpolation**

Interpolate only x/y positions for matching aircraft between two snapshots with increasing simulation times. Clamp fraction to `[0,1]`; all modes, routes, battery, links, contacts, and alerts come from the newer snapshot. Return new objects and deep-freeze inputs in tests to prove no mutation.

- [ ] **Step 6: Run focused and full frontend tests**

```bash
cd webui/frontend
npm test -- --run src/lib/simulation/stream.test.ts src/lib/simulation/store.test.ts src/lib/simulation/interpolation.test.ts
npm test -- --run
npm run typecheck
```

Expected: PASS.

- [ ] **Step 7: Commit and push Task 3**

```bash
git add webui/frontend/src/lib/simulation/stream.ts webui/frontend/src/lib/simulation/store.ts webui/frontend/src/lib/simulation/interpolation.ts webui/frontend/src/lib/simulation/stream.test.ts webui/frontend/src/lib/simulation/store.test.ts webui/frontend/src/lib/simulation/interpolation.test.ts
git diff --cached --check
git commit -m "feat(frontend): manage ordered simulation telemetry"
git push origin HEAD
```

### Task 4: Offline tactical SVG map and keyboard navigation

**Files:**
- Create: `webui/frontend/src/components/mission/map/projection.ts`
- Create: `webui/frontend/src/components/mission/map/projection.test.ts`
- Create: `webui/frontend/src/components/mission/map/MissionMap.tsx`
- Create: `webui/frontend/src/components/mission/map/MissionMap.test.tsx`
- Create: `webui/frontend/src/components/mission/map/MapToolbar.tsx`
- Create: `webui/frontend/src/components/mission/map/AircraftSymbol.tsx`
- Create: `webui/frontend/src/components/mission/map/ContactSymbol.tsx`

**Interfaces:**
- Consumes: public `WorldSnapshot`, selected IDs, locale, and display-only interpolation.
- Produces: accessible `MissionMap`, deterministic mission-to-SVG projection, pan/zoom/reset/layer state, aircraft/contact selection callbacks.

- [ ] **Step 1: Write failing projection and semantic-map tests**

```ts
it("projects mission millimetres into an SVG viewBox with y inversion", () => {
  const project = createProjection({ min_x_mm: 0, min_y_mm: 0,
    max_x_mm: 12_000_000, max_y_mm: 8_000_000 }, { width: 1200, height: 800 });
  expect(project.point({ x_mm: 6_000_000, y_mm: 2_000_000 }))
    .toEqual({ x: 600, y: 600 });
});

it("renders labels and non-color status for aircraft and detected contacts", () => {
  render(<MissionMap snapshot={snapshot} locale="en" onSelectAircraft={onAircraft}
                     onSelectContact={onContact} />);
  expect(screen.getByRole("img", { name: /tactical mission map/i })).toBeVisible();
  expect(screen.getByRole("button", { name: /UAS-01.*link nominal/i })).toBeVisible();
  expect(screen.getByRole("button", { name: /contact C-01.*detected/i })).toBeVisible();
  expect(screen.queryByText(/priority truth/i)).not.toBeInTheDocument();
});

it("supports keyboard aircraft selection and reset view", async () => {
  renderMap();
  await user.tab();
  await user.keyboard("{Enter}");
  expect(onAircraft).toHaveBeenCalledWith("UAS-01");
  await user.click(screen.getByRole("button", { name: /reset view/i }));
  expect(screen.getByTestId("map-root")).toHaveAttribute("data-zoom", "1");
});
```

- [ ] **Step 2: Run map tests and confirm missing components**

Run: `cd webui/frontend && npm test -- --run src/components/mission/map/MissionMap.test.tsx src/components/mission/map/projection.test.ts`

Expected: FAIL resolving map modules.

- [ ] **Step 3: Implement pure projection and bounded viewport transforms**

`createProjection(bounds, viewport)` returns `point`, `polygon`, `route`, `missionDistanceToPixels`, and inverse point functions. Maintain pan/zoom in component-local state; clamp zoom `[0.75, 6]` and pan so at least 20% of terrain remains visible. Reset restores scenario initial view. Pointer-wheel zoom must be prevent-default only while over the map; keyboard `+`, `-`, arrow keys, and `0` provide zoom/pan/reset.

- [ ] **Step 4: Implement ordered SVG layers and accessible symbols**

Render layers in this order: background/grid, terrain boundary, restricted zones, sectors, coverage, routes, sensor footprints, conflict lines, contacts, aircraft, home base, labels. Each selectable symbol is an SVG `<button>` equivalent using `role="button"`, `tabIndex=0`, translated `aria-label`, Enter/Space activation, visible focus ring, text/shape status marker, and minimum 24 px hit target. Only DETECTED/INSPECTABLE contact position is present because backend snapshots omit undetected contacts.

MapToolbar toggles routes, sensors, coverage, contacts, and labels locally; it cannot send commands. Respect `prefers-reduced-motion` by disabling interpolation transitions.

- [ ] **Step 5: Run map, store, type, and build checks**

```bash
cd webui/frontend
npm test -- --run src/components/mission/map/MissionMap.test.tsx src/components/mission/map/projection.test.ts
npm run typecheck
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit and push Task 4**

```bash
git add webui/frontend/src/components/mission/map
git diff --cached --check
git commit -m "feat(frontend): render offline tactical mission map"
git push origin HEAD
```

### Task 5: Fleet, commands, alerts, contacts, live mission console, and Phase 4 gate

**Files:**
- Create: `webui/frontend/src/components/mission/MissionTopBar.tsx`
- Create: `webui/frontend/src/components/mission/FleetPanel.tsx`
- Create: `webui/frontend/src/components/mission/CommandBar.tsx`
- Create: `webui/frontend/src/components/mission/AlertQueue.tsx`
- Create: `webui/frontend/src/components/mission/ContactQueue.tsx`
- Create: `webui/frontend/src/components/mission/MissionConsole.tsx`
- Create: `webui/frontend/src/components/mission/MissionConsole.test.tsx`
- Create: `webui/frontend/src/app/mission/page.tsx`
- Modify: `webui/frontend/src/app/globals.css`
- Modify: `webui/frontend/src/components/ui/button.tsx`

**Interfaces:**
- Consumes: session API, stream/store, map, translation, authoritative valid states.
- Produces: complete `/mission` operational workflow through Phase 3 backend.

- [ ] **Step 1: Write failing console workflow and alert-order tests**

```tsx
it("orders critical unacknowledged alerts before advisory and acknowledged", () => {
  render(<AlertQueue alerts={mixedAlerts} locale="en" onAcknowledge={ack} />);
  expect(screen.getAllByRole("listitem").map(row => row.dataset.alertId))
    .toEqual(["critical-new", "advisory-new", "critical-acked", "advisory-acked"]);
});

it("shows only mode-valid commands and submits authoritative state version", async () => {
  renderConsole(snapshotWithSelectedSearchingAircraft());
  expect(screen.getByRole("button", { name: /hold/i })).toBeEnabled();
  expect(screen.getByRole("button", { name: /resume mission/i })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: /return to base/i }));
  await user.click(screen.getByRole("button", { name: /confirm return/i }));
  expect(mockSubmit).toHaveBeenCalledWith(expect.objectContaining({
    expected_state_version: 44,
    kind: "RETURN_TO_BASE",
    payload: { aircraft_id: "UAS-01" },
  }));
});

it("completes the non-kinetic contact workflow without hidden truth", async () => {
  renderConsole(inspectableContactSnapshot());
  await user.click(screen.getByRole("button", { name: /inspect C-01/i }));
  expect(mockSubmit).toHaveBeenCalledWith(expect.objectContaining({ kind: "INSPECT_CONTACT" }));
  expect(document.body).not.toHaveTextContent("truth");
  expect(screen.queryByText(/engage|weapon|targeting/i)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run the console test and confirm missing components**

Run: `cd webui/frontend && npm test -- --run src/components/mission/MissionConsole.test.tsx`

Expected: FAIL resolving `MissionConsole`.

- [ ] **Step 3: Implement the panels with authoritative status and stable sorting**

- `MissionTopBar`: session/profile/timer, connection text+shape, locale display, pause/resume/finish with confirmation.
- `FleetPanel`: lexical aircraft order; task, link, battery/reserve, sensor, route, and highest alert; keyboard selection.
- `CommandBar`: sector selector, map waypoint mode, hold, resume, RTB; command UUID via `crypto.randomUUID()`; destructive RTB confirmation; disabled explanation text.
- `AlertQueue`: exact approved ordering then opening sequence; acknowledge only unacknowledged items.
- `ContactQueue`: evidence/workflow order; inspect, classification (`routine|priority|uncertain`), priority (`LOW|MEDIUM|HIGH`), report-note code, correction linked to latest report.

Every async action shows a pending ID but does not optimistically change authoritative status. Stable backend error codes render through `t()` and retain a diagnostics code for the researcher.

- [ ] **Step 4: Compose the full-screen live route**

`/mission` reads `session` from query params, fetches session/state, retrieves the lease from session storage, chooses controller or observer mode, starts `SimulationStream`, and disconnects on unmount. Missing session redirects to setup; missing lease offers read-only observer mode rather than fabricating control. The grid uses:

```text
top bar: full width
left: 18rem fleet
center: minmax(0, 1fr) map
right: 22rem alerts/contacts tabs
bottom: command bar spanning center/right
```

At 1280×720, right detail becomes an accessible drawer and map stays at least 640×420. Add mission-specific CSS under `.simulation-console`; do not globally alter existing page layouts. Add an `aria-busy` style and a critical button variant if needed.

- [ ] **Step 5: Verify component behavior, all frontend tests, typecheck, and production build**

```bash
cd webui/frontend
npm test -- --run src/components/mission/MissionConsole.test.tsx
npm test -- --run
npm run typecheck
npm run build
```

Expected: all PASS; `/mission` and `/mission/setup` build; existing routes remain.

- [ ] **Step 6: Run backend/frontend smoke in the headless environment**

Start the backend on `127.0.0.1:8000` and frontend on `127.0.0.1:3100`, then use the installed headless browser tooling to verify `/mission/setup` returns 200, renders the scenario, and has no console errors. Stop both processes cleanly. Full browser automation lands in Phase 6.

- [ ] **Step 7: Commit and push the Phase 4 gate**

```bash
git add webui/frontend/src/components/mission webui/frontend/src/app/mission/page.tsx webui/frontend/src/app/globals.css webui/frontend/src/components/ui/button.tsx
git diff --cached --check
git commit -m "feat(frontend): deliver live sUAS mission console"
git push origin HEAD
```
