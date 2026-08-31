# Component licenses

This repository is multi-licensed by component. The root `LICENSE` applies to
original MIT-licensed components unless a nearer license or file notice states
otherwise. The embedded and modified OpenMATB tree is governed by
`openmatb/LICENSE` (CeCILL v2.1); its copyright and provenance notices must be
preserved in every source or binary redistribution.

No root-level license statement relicenses third-party software. Release tooling
must include both license texts and `THIRD_PARTY_NOTICES.md`.

`component-map.json` is the machine-readable path-to-license map. Its most
specific path prefix wins, while a nearer license or source-file SPDX notice
always takes precedence. The map documents distribution boundaries; it is not
a substitute for the independent licensing review that remains a release gate.
