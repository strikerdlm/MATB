# Three.js geographic presentation

The [Colombia geography and traffic extension](colombia-geography-traffic.md)
adds the national explorer, five regional packages, layers and captured traffic.

The sUAS console supports a versioned offline 3D condition alongside its default
SVG map. It uses Three.js 0.186.0 inside the existing Next.js/React application.
The backend remains the authority for aircraft motion, contacts, events, scoring,
questionnaires and replay. This is a synthetic research presentation; there is
no terrain collision, line-of-sight detection or physical imaging model.

## Run

Use the existing MATB backend and frontend launch commands. Install frontend
packages with `npm ci` in `webui/frontend`, then `npm run build` and `npm start`.
The included `public/scenes/villavicencio-v1` package is served locally and needs
no account, API key or network during a mission. `GET /simulation/scenes` lists
only packages whose manifests and files pass validation.

On **mission setup** or **technical tests**, choose Villavicencio under Local
scene, then choose 2D/3D for each block. Prepare the session. A 3D block first
loads and verifies its scene and creates a WebGL renderer; Start is rejected by
the backend until readiness is recorded. Research conditions are immutable for
the session. Technical mode allows an explicit 2D fallback. Old sessions and
requests without presentation metadata use 2D.

Inside 3D, choose Overview, Follow or Drone camera. Select aircraft through the
fleet panel or scene. Waypoints use the existing command workflow and controller
lease. Arrows pan, +/- zoom and 0 resets the overview. Procedural aircraft are
schematic and enlarged for visibility. The drone camera looks down and forward;
it is not a camera used by the detection model. Satellite pixels are about 10 m,
so people and fine inspection details cannot be resolved.

## Coordinates and assets

The scenario center (6000 m east, 4000 m north) maps to 4.15 N, 73.65 W. Assets
are reprojected to a WGS84 azimuthal-equidistant local grid with a 2 km margin.
Mission millimetres become metres with Three.js X=east, Y=up, Z=-north. Terrain
heights use the source EGM96 reference. Configured aircraft `altitude_mm` is
rendered as illustrative height above sampled terrain, without altering engine
state or introducing vertical flight dynamics. Terrain is sampled on a 100 m
grid; scenery geometry and drone meshes are constructed at runtime.

`manifest.json` records product IDs, acquisition times, source URLs, source
checksums, a fixed RGB display stretch, grid sizes and file checksums. The
manifest hash is pinned in each session. Missing coverage or corrupt files block
readiness. No runtime fallback to remote tiles is implemented.

Rebuild a *new version* in an isolated Python 3.12 environment:

```powershell
python -m pip install -r requirements-suas-scene.txt
python scripts/package_suas_scene.py --end-date 2026-09-08 --product-id S2B_18NXK_20260810_0_L2A --output webui/frontend/public/scenes/villavicencio-rebuild
```

The packager refuses to overwrite an existing directory. Automatic selection
uses Sentinel-2 scene classification (cloud classes 8/9/10) sampled over the
12 by 8 km mission footprint at 100 m, with newest acquisition as the tie break.
The selected scene has 0% cloud-class samples on this grid; this does not prove
that every 10 m image pixel is cloud-free. Source scale and offset are applied
before the fixed RGB display stretch. For EarthSearch products declaring
`earthsearch:boa_offset_applied`, the already-applied offset is not subtracted
a second time; this provenance flag is retained in the package. Pin `--product-id` to reproduce acquisition selection.
Source tile versions can change upstream; session reproducibility relies on
retaining the actual checksummed package. RGB contrast is a fixed visualization
stretch, not a calibrated radiometric product.

Attribution: contains modified Copernicus Sentinel data. Terrain from Mapzen /
Tilezen with SRTM and contributing sources. See manifest source terms and
https://github.com/tilezen/joerd/blob/master/docs/attribution.md. No Google or
Esri tiles, API credentials, external model files, or live OSINT feeds are used.

## Public interfaces and recording

Session creation accepts optional `presentation`:

```json
{"version":1,"blocks":{"PRACTICE":"2d","LOW":"3d","MEDIUM":"2d","HIGH":"3d"},"scene_id":"villavicencio-v1","scene_sha256":"<manifest SHA-256>","camera":"overview"}
```

Session responses and debriefs expose this configuration. No database migration
is required: it is stored in the existing immutable manifest JSON.
`POST /simulation/sessions/{id}/presentation` requires the existing controller
lease and strict bounded event fields. It records ready/camera/render/failure/
fallback events in `presentation.jsonl`, separately from authoritative events.
It includes camera pose, selected aircraft, simulation coordinates and browser
presentation timing. Render samples are throttled to two seconds. These timing
samples are browser observations, not physical display measurements.

The presentation log is included in artifact checksums and the public bundle.
Research rendering failures revoke readiness, pause the session and record a
protocol deviation. A fresh successful readiness check is required to resume.
SAGAT unmounts operational views and hides the command bar. Contacts are built
only from redacted snapshots containing evidence and a public position.

Replay regenerates redacted frames at the engine snapshot cadence from verified
effective command records. Block order follows the session manifest rather than
sorting reset clocks across blocks. Debrief supports block selection, playback,
seeking, technical 2D fallback and recorded camera mode/pose playback. Camera
poses are sampled every two seconds; this does not reproduce every rendered
frame or physical display latency. Older recordings without scene
metadata remain 2D; unverified recordings retain the existing checkpoint view.

## Upstream relationship

God's Eye View (https://github.com/bilawalsidhu/gods-eye-view) was inspected as an
architectural reference for independently managed geographic layers and camera
ownership. Its renderer is Cesium-based. This implementation is new TypeScript
code for MATB; no upstream source files or Cesium runtime were copied. Future
source adaptations must pin the upstream commit and preserve its MIT notices.
The procedural-modeling skill applies to the drone mesh builders; geographic
imagery is a separate licensed data pipeline.

## Verification

Run the presentation tests with the existing MATB Python environment and the
frontend's Vitest/Playwright tooling. See `suas-threejs-verification.md` for the
measured results and outstanding physical-station validation.

## Presentation v2

See [Presentation v2 and camera/contact management](suas-presentation-v2.md) for resolved exposure records, version compatibility, opt-in interaction controls, and replay qualification.
