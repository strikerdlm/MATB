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
