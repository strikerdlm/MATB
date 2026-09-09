# Third-party notices

## OpenMATB

- Component: `openmatb/`
- Version reported by the component: 1.4.5
- License: CeCILL v2.1
- License text: `openmatb/LICENSE`
- Redistribution rule: preserve the upstream license, copyright notices and the
  provenance of repository modifications. The root MIT license does not replace
  the component license.

## Python and JavaScript dependencies

The optional Colombia presentation uses Three.js, MapLibre GL JS, proj4 and
pyproj. The frontend build copies MapLibre's installed worker/shared modules
and its license to a generated directory; generated dependency files are not
committed. God's Eye View informed the traffic-layer design; MATB uses its own
adapters and does not vendor that application's source.

### Geographic datasets

`webui/frontend/public/scenes/` contains derived Sentinel-2 imagery, Mapzen/Tilezen
terrain and geographic overlays. `webui/frontend/public/geography/` contains
OurAirports reference data, region metadata and an EGM96 separation grid.
Dataset-specific terms apply to source and derived data; the repository's MIT
license does not replace them. Per-asset hashes, source URLs and acquisition
metadata are retained in the scene manifests and reference catalog.

- Copernicus Sentinel: https://dataspace.copernicus.eu/terms-and-conditions
- Terrain contributors: https://github.com/tilezen/joerd/blob/master/docs/attribution.md
- OpenStreetMap/OpenFreeMap overlays: https://www.openstreetmap.org/copyright
- OurAirports reference data: https://ourairports.com/data/
- EGM96 source grid: https://cdn.proj.org/us_nga_egm96_15.tif
- Online imagery: https://nasa-gibs.github.io/gibs-api-docs/
- Observed traffic: https://www.adsb.lol/privacy-license/ and https://openskynetwork.github.io/opensky-api/rest.html

Live traffic captures are local runtime artifacts and are not committed.
Preserve the applicable source attribution when distributing scene data or captures.

Runtime and development dependencies retain their respective upstream licenses.
The public-release workflow must generate a dependency inventory/SBOM from the
locked release environment and must not treat this notice as a substitute for
that generated evidence.

## Polar BLE SDK protocol reference

- Scoped source: `matb_integration/physiology/broadcast.py`
- Upstream: `polarofficial/polar-ble-sdk`
- License: `LicenseRef-Polar-SDK`
- License text: `LICENSES/Polar_SDK_License.txt`
- Use: Polar manufacturer HR advertisement decoding only. MATB is not
  affiliated with or endorsed by Polar Electro.

## HRV calculation source

- Scoped source: `matb_integration/physiology/analysis.py`
- Upstream: `strikerdlm/HRV`
- Revision: `ef086092cfc57c74171f9ac9374b8ba24ceb0e6a`
- License: MIT
- License text: `LICENSES/HRV-MIT.txt`
- Modification: the Release A port uses conservative artifact rejection and
  continuity breaks; it does not claim the upstream class-aware structural
  correction identifier.
