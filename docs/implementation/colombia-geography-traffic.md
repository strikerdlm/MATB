# Colombia geography and observed traffic

MATB now has a Colombia explorer at **`/colombia`**, six local geographic scenes,
and observed aircraft traffic in the explorer and interactive technical missions.
The mission view uses Three.js and TypeScript. The national explorer uses
MapLibre GL JS; MATB remains the authority for simulation, commands and scoring.

## Start and use

Install the backend requirements in the existing MATB environment. From the
repository root, in a terminal using that Python environment:

```powershell
python -m pip install -r webui/backend/requirements.txt
cd webui/backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
# From the repository root
cd webui/frontend
npm ci
npm run build
npm start
```

Open **http://localhost:3100/colombia**. Choose a region or enter coordinates;
the amber rectangle marks the 12 × 8 km local mission footprint. Choose layers,
inspect an aerodrome, or select a traffic observation for its source time,
altitudes and ground speed. A dashed outline marks the traffic query area,
capped at 250 NM. At national scale this is a bounded query around the view
center, not an assertion of complete nationwide aircraft coverage.

The geography endpoints belong to the optional `matb-suas` component. Use the
default `MATB_COMPONENTS=auto` composition; `MATB_COMPONENTS=core` excludes them.

To launch a mission, use **Technical test** on an installed scene card. Select
**Traffic → Live** and the provider, then prepare and start the block after 3D
readiness succeeds. Overview, Follow and Drone cameras track MATB aircraft.
Observed traffic has separate selection and detail controls; it cannot receive
MATB aircraft commands.

| Region | Local scene | Origin latitude, longitude |
| --- | --- | --- |
| Meta | Villavicencio | 4.1500, -73.6500 |
| Cauca | Popayán | 2.4448, -76.6147 |
| Norte de Santander | Cúcuta | 7.8939, -72.5078 |
| Antioquia | Rionegro | 6.1533, -75.3742 |
| Sierra Nevada de Santa Marta | Minca | 11.1430, -74.1160 |
| Sierra Nevada del Cocuy | El Cocuy–Güicán | 6.4220, -72.4280 |

The explorer also offers San Andrés and Providencia and arbitrary coordinates
within its Colombia extent. Named scenes cover local areas; they do not contain
a whole department or mountain range offline.

## Layers and provenance

| Layer | National explorer | Local mission |
| --- | --- | --- |
| Basemap, roads, rivers, settlements, boundaries | OpenFreeMap / OpenMapTiles / OpenStreetMap | Pinned, clipped vector features in the five new packages |
| Airports and heliports | 722 non-closed OurAirports entries for Colombia | Entries inside each new scene footprint and margin |
| Satellite imagery | NASA GIBS MODIS Terra, nominal 250 m, recent daily acquisition | Pinned Sentinel-2 L2A RGB, 10 m sampling |
| Relief | Mapzen / Tilezen Terrarium hillshade | 100 m terrain grid with a 2 km margin |
| Observed traffic | Live, source status and observation age | Off, live technical exposure, or immutable captured exposure |

The original Villavicencio v1 package retains its terrain and imagery; the five
new scene packages also contain vector overlays. Layer completeness follows the
source data. These layers are geographic context, not aeronautical charts.
Boundaries and airports are not evidence of current airspace restrictions.

Manifests retain acquisition dates, source URLs, per-file SHA-256 hashes,
projection, radiometry and sampled cloud fraction. Cloud selection covers the
mission plus margin before scoring the mission footprint. Very sparse missing
RGB values remain transparent, with no imputation; a candidate is rejected if
more than 0.01% of RGB pixels are missing. The manifest reports valid coverage.
A sampled cloud fraction of 0% does not establish cloud-free imagery at every
pixel, especially in the surrounding margin.

The national layer URLs and content can change. Local packages are immutable:
new acquisitions must use a new scene ID. The EGM96 separation grid and reference
catalog have recorded checksums in `public/geography/catalog.json`.

## Prepare another offline area

Only preparation needs the optional geospatial Python environment. It is
separate from the experiment environment to keep GDAL and NumPy upgrades scoped:

```powershell
# From the repository root, using Python 3.12
python -m venv .venv-geography
.\.venv-geography\Scripts\python.exe -m pip install -r requirements-suas-scene.txt
.\.venv-geography\Scripts\python.exe -m pip check
```

The scene requirements pin NumPy 2.4.6, matching the Windows release lock and
Numba 0.65.1's `numpy<2.5` requirement. If an earlier scene installation upgraded
NumPy to 2.5.3 in the MATB environment, activate that affected environment and
restore the compatible version:

```powershell
python -m pip install "numpy==2.4.6"
python -m pip check
```

Restart the backend if changing its environment configuration. It automatically
finds `.venv-geography`; `MATB_GEOGRAPHY_PYTHON` can point to another executable.
On the Colombia page, select a center, name the area and click **Prepare offline
area**. The job reports progress and supports cancellation. Only a completed,
verified package appears in the scene catalog. New assets are served by the
backend immediately, including when the Next.js frontend is a production build.

A command-line equivalent, with a new output ID:

```powershell
.\.venv-geography\Scripts\python.exe scripts/package_suas_scene.py --output webui/frontend/public/scenes/my-area-v1 --lat 6.1533 --lon -75.3742 --title "Mi área" --region Antioquia --end-date 2026-09-08
```

Preparation can fail when imagery lacks sufficient coverage, public services
are unavailable, or dependencies are missing. It does not substitute synthetic
imagery. Interrupted job status is not restored after a backend restart; prepare
the area again. Staging directories are excluded from the installed catalog.

## Traffic and experimental timing

The default adapter queries adsb.lol's bounded `/v2/point/lat/lon/radius` endpoint.
It shares concurrent identical requests and caches each query for 15 seconds,
retains provider and receipt times, observes rate-limit backoff, and distinguishes
an empty response from an unavailable source. No API key is needed by this adapter.

OpenSky is an optional configured provider. Set `OPENSKY_CLIENT_ID` and
`OPENSKY_CLIENT_SECRET` in the backend process environment. OAuth tokens and
credentials remain on the server. The OpenSky normalization is unit-tested;
authenticated access was not exercised without credentials.

Positions extrapolate only through the first 15 seconds after an observation,
using reported heading and speed. Older observations are marked stale and stop
moving; they disappear after 60 seconds. Missing velocity remains missing.
Barometric altitude is never relabeled geometric altitude. A track without
geometric altitude appears in the national/2D map and traffic list, with no
invented 3D height. Geometric height is converted to EGM96 orthometric height
before comparison with terrain. Grounded observations remain stationary.

Network acquisition runs outside the simulation lock and never drives engine
ticks or seeded sensors. Pause and SAGAT concealment suspend traffic exposure;
resumption marks a trail discontinuity. Terrain and observed traffic do not
change detection, separation scoring, battery calculations or aircraft dynamics.

## Capture, reuse and replay

1. Run an interactive technical session with live traffic for at least the
   duration needed by the intended research blocks, then finish it.
2. In its debrief, enter a recording name and choose **Save capture**, before
   preparing another session. This requires the original controller lease and
   verified sealed artifacts with actual aircraft observations.
3. In research setup, choose the same geographic scene and **Recorded real
   traffic**. The recording ID and SHA-256 are pinned in the session manifest.
   The backend rejects live traffic for research, a different scene/provider,
   a mismatched checksum or a recording shorter than the block.

Captures are saved under `outputs/geography/recordings` by default; set
`MATB_GEOGRAPHY_DIR` to use another local root. A run embeds its verified source
as `traffic-source.json`. Removing a capture from the catalog does not remove
that run's embedded source. Captured projected positions and converted heights
are reused without recomputing them against a future geoid grid.

Traffic frames use simulation timestamps and are saved to `traffic.jsonl`,
separate from deterministic engine events. Artifact checksums cover traffic and
presentation logs; public replay includes exposed traffic frames. Camera/render
samples reference the traffic frame ID and configured layers. Replay uses these
captured frames and never contacts a live provider. Source capture files are
not added to the public artifact bundle.

The geographic display adds visual context. It does not establish physical,
human-performance or operational validity. The existing low/medium/high fleet
presets still need human calibration.

## Implementation and checks

- `webui/backend/app/traffic_service.py`: bounded acquisition, normalization,
  caching, staleness and immutable capture loading.
- `webui/backend/app/routers/geography.py`: catalog, verified asset delivery,
  preparation jobs, traffic queries and capture promotion.
- `webui/frontend/src/components/geography`: national explorer and controls.
- `webui/frontend/src/lib/geography`: coordinate conversion and Three.js layers.
- `scripts/package_suas_scene.py`: bounded, staged, source-hashed preparation.

MapLibre 6 uses ESM workers. Build/dev hooks copy its worker, shared module and
license from the pinned installation to `public/maplibre`; the page sets the
worker URL explicitly. Both files are required by the current Next.js bundler.
[MapLibre installation instructions](https://maplibre.org/maplibre-gl-js/docs/).

Validation evidence and screenshots: [Colombia verification](colombia-geography-verification.md).
The original camera integration is documented in [Three.js presentation](suas-threejs-presentation.md).

## Sources and terms

The traffic-layer architecture was informed by the [God's Eye View flight
module](https://github.com/bilawalsidhu/gods-eye-view/blob/main/src/data/flights.js).
MATB implements its own Python acquisition and TypeScript presentation adapters;
the GEV Cesium application and its live intelligence layers are not dependencies.

- [adsb.lol API](https://api.adsb.lol/docs) and [data licensing](https://www.adsb.lol/privacy-license/).
- [OpenSky REST API](https://openskynetwork.github.io/opensky-api/rest.html).
- [OpenFreeMap](https://openfreemap.org/) and [OpenStreetMap attribution and ODbL](https://www.openstreetmap.org/copyright).
- [OurAirports public-domain data](https://ourairports.com/data/).
- [NASA GIBS imagery](https://nasa-gibs.github.io/gibs-api-docs/).
- [Earth Search Sentinel-2 catalog](https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a) and [Copernicus terms](https://dataspace.copernicus.eu/terms-and-conditions).
- [Mapzen / Tilezen terrain attribution](https://github.com/tilezen/joerd/blob/master/docs/attribution.md).
- [PROJ EGM96 grid](https://cdn.proj.org/us_nga_egm96_15.tif).

Source terms and public-service availability remain separate from MATB's code
license. Retain dataset attribution when distributing captured traffic or scene
packages; review provider terms for the intended institutional use.
