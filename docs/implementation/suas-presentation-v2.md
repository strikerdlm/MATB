# Presentation v2 and camera/contact management

This extension keeps Python-owned task state, public presentation snapshots, separate traffic captures, and MATB-owned SVG/Three.js renderers. It adds no GEV runtime, Cesium dependency, provider, sensor model, or scoring behavior.

## Configure a condition

New selections in Presentation Setup emit `version: 2`. The setup exposes three explicit opt-ins:

```json
"controls": {
  "smooth_camera": false,
  "contact_cycling": false,
  "adjustable_layers": false
}
```

These settings are bound into the existing session manifest. Camera mode selection and existing aircraft/contact selection remain available. Smooth transitions use 600 ms smoothstep position interpolation and quaternion slerp; a reduced-motion preference resolves the effective duration to zero. Contact cycling uses stable identifiers within simulated-aircraft, public-contact, and observed-aircraft groups. Cycling in Overview does not redirect the camera. Follow can target simulated or observed aircraft; Drone remains a simulated-aircraft viewpoint. Task contacts support inspection only.

Observed selection and camera focus never replace the simulated aircraft selected for commands. Commands still use the existing lease and expected-state-version workflow. Public contact eligibility requires position and non-`NONE` evidence. Observations retain their existing freshness, altitude-reference, extrapolation, and capture rules. No invented sensor measurements are displayed.

## State and recording contract

`ResolvedPresentation` is renderer-independent, versioned separately from engine state, and held for the session/block across SAGAT component unmounts. It includes:

- Renderer condition, selected simulated aircraft/task contact/observed aircraft, categorized focus, and navigation category.
- Operational layer switches and geographic layer selection; availability remains determined by the renderer and pinned package. The SVG map has no geographic overlay renderer.
- Camera mode, sampled pose, perspective FOV/aspect, effective transition duration, and 2D zoom/pan.
- Viewport dimensions/effective DPR, visible/hidden/concealed/unavailable status, scene and capture checksums, standard visual-profile version, and procedural model version/scale.

The existing `POST /simulation/sessions/{id}/presentation` accepts v1 or v2 records. V2-configured sessions require v2 records. Each v2 event contains a full resolved snapshot, event UUID, increasing sequence, client monotonic time mapped through `performance.timeOrigin`, client simulation time/state version, traffic-frame reference, and server receipt metadata. These timestamps describe software observations, not physical stimulus onset.

Discrete changes are recorded immediately. Camera samples are bounded to approximately one per two seconds, plus transition start/end/interruption and manual-input completion. Full snapshots allow backward seeking without replaying mutable UI history. The ordered delivery queue retains at most 128 pending events and retries an unchanged event ID three times. It survives SAGAT remounts. Each delivery attempt has a five-second transport timeout. Completing a session freezes the view and waits up to 20 seconds for pending exposure acknowledgements before sealing; a failed queue prevents completion. Overflow or delivery failure reports a presentation failure and blocks local controls. Backend capacity exhaustion or write failure clears readiness and pauses research before further recording attempts; transport loss continues to use the existing connection safeguards. Reload and requalify the presentation after a recording failure; no silent queue reset is provided.

The backend checks version, finite projection values, normalized quaternions, pinned assets, layer permissions, navigation opt-in, sequence, and categorized selection eligibility. Validation checks newly selected entities against currently permitted public state; existing selections can survive delayed receipt until a renderer emits target loss. The presentation record remains distinct from authoritative command acceptance and engine replay.

## Replay and concealment

The replay timeline incorporates presentation changes alongside public engine frames. Multiple changes at one simulation time retain their sequence and software-time spacing. Forward/backward seeking restores the recorded resolved state. Pose interpolation uses compatible samples only; it does not cross concealed intervals, renderer changes, or different camera targets. This is reconstructed camera motion, not a recording of every rendered frame.

Recorded replay disables presentation controls. An explicit exploratory mode allows separate inspection and emits no presentation records or simulator commands. Concealed, hidden, and unavailable exposures show no operational scene or contact cards. Three.js replay preserves recorded aspect ratio; effective physical pixel density still depends on the replay device. The SVG map retains its fixed logical view box.

V1 sessions remain readable with their original defaults. Replay explicitly identifies operational layers and observed selection as unknown for legacy recordings; it does not claim that inferred defaults were measured exposure. Engine determinism remains a separate guarantee.

## Camera lifecycle and provenance

One camera owner is active: manual, transition, follow, drone, or replay. Manual takeover cancels automated motion without resetting pose. Reset uses the existing overview preset. A disappearing target ends follow without selecting another entity. Animation frames are requested only while a transition owns motion; scene updates and manual interaction retain demand-driven rendering. Freeze, renderer failure, and disposal cancel transition work.

Behavioral reference: [GEV cameraVerbs.js at 759652207fd1279ece97f0f19af566feb9a82146](https://github.com/bilawalsidhu/gods-eye-view/blob/759652207fd1279ece97f0f19af566feb9a82146/src/cameraVerbs.js). The controller and reducer are MATB implementations; no GEV source or third-party assets were copied. Scene, imagery, terrain, and geographic attribution remain governed by their existing manifests and notices.

## Verification and qualification

Automated coverage includes backward/equal-time seeking, legacy replay, category isolation, camera interruption/completion, stale render callbacks, queue ordering/retries/capacity, backend permissions/readiness, offline browser presentation, and engine equivalence with identical inputs. Run the relevant presentation Vitest/Playwright suites and backend simulation-runtime/geography/replay tests.

For an isolated frontend build on a workstation with an existing `.next` directory, set `MATB_NEXT_DIST_DIR=.next/presentation-v2-final` consistently for build and start. The default remains `.next`.

Browser software tests do not establish GPU completion, physical display latency, or human validity. Research deployment still requires the target workstation's rendering/timing qualification and a separately specified human-factors protocol. Annotations, scene-director debrief, HUD-density experiments, thermal/NVG palettes, new models/providers, and voice remain later milestones.

### Local verification, 2026-09-09

- Backend simulation-runtime, geography, and deterministic replay suites: 38 passed. After final contract/failure-path changes, the 15 simulation-runtime tests passed again.
- Frontend presentation/debrief suites: 17 passed. Typechecking and ESLint completed without errors; the isolated production build succeeded.
- Browser acceptance: 7 passed, covering v2 controls and observed follow, offline replay, v1 LOW/MEDIUM/HIGH presentations, corrupt-asset rejection, and SAGAT concealment/sealed replay under both contract versions. Traffic came from the repository's explicit synthetic provider fixture.
- Browser: Chromium 151.0.7922.34, ANGLE/Vulkan SwiftShader, 1920 × 1080, effective DPR 1 for the recorded desktop diagnostic. This software-rendered acceptance run is not a qualification of the research workstation's GPU or physical display.

The browser log and screenshots/renderer diagnostics are retained locally under `webui/frontend/.next/presentation-v2-acceptance.log` and `webui/frontend/.next/presentation-v2-acceptance-results/`; these generated artifacts are not source files or publication evidence.
