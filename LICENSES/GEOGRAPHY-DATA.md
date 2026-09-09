# Geographic data terms and attribution

`LicenseRef-Geographic-Data` identifies a collection with source-specific terms.
It is not a new license grant and does not apply the repository MIT license to
upstream geographic data. Repository-authored code retains its own license.

The `webui/frontend/public/geography/` catalog and each
`webui/frontend/public/scenes/` manifest identify sources, acquisition dates and
checksums. Preserve those manifests when distributing derived scene packages.

| Data | Source terms and attribution |
| --- | --- |
| Sentinel-2 L2A imagery | Contains modified Copernicus Sentinel data. See [Copernicus data access and legal notice](https://dataspace.copernicus.eu/terms-and-conditions). Acquisition dates are in each scene manifest. |
| Terrarium elevation | Mapzen / Tilezen terrain tiles; global SRTM and GMTED2010 elevation courtesy of the U.S. Geological Survey, and ETOPO1 courtesy of NOAA. See [Tilezen terrain attribution](https://github.com/tilezen/joerd/blob/master/docs/attribution.md). |
| Roads, water, places and boundaries | © OpenStreetMap contributors, [ODbL](https://www.openstreetmap.org/copyright), distributed through [OpenFreeMap](https://openfreemap.org/) / OpenMapTiles. |
| Aerodromes | [OurAirports open data](https://ourairports.com/data/), released to the public domain; the pinned catalog excludes closed entries. |
| EGM96 separation grid | PROJ distribution of the public-domain NGA EGM96 grid; see the [PROJ grid metadata](https://cdn.proj.org/us_nga_README.txt). |

The online explorer also requests NASA GIBS imagery and provider traffic. These
responses are not included as a national offline dataset. See
[NASA GIBS](https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api),
[adsb.lol CC0 terms](https://www.adsb.lol/privacy-license/) and
[OpenSky terms](https://opensky-network.org/about/terms-of-use).
Recorded traffic captures retain their provider attribution and source terms.

For layer scope and preparation instructions, see the
[Colombia geography guide](../docs/implementation/colombia-geography-traffic.md).
