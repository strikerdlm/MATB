# Draft flight-plan export format

Flight-plan exports from `@fac-isr/geo` are offline planning artifacts. They preserve route geometry, WGS 84 coordinates, altitude reference, source package IDs, and safety-check results.

Supported formats are JSON, GeoJSON, KML, KMZ, GPX, and a bilingual human-readable text view. Every draft carries `transmission: "not-supported"`. The package exposes no transmit, command, dispatch, or GCS adapter operation; an export cannot be sent to an aircraft or ground-control station.

Altitude values are retained without rounding. GeoJSON coordinates use `[longitude, latitude, altitude]`; KML uses absolute altitude with the draft's declared altitude reference retained in metadata. KMZ is a ZIP containing `doc.kml`.
