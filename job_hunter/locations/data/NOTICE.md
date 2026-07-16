# GeoNames attribution

The city files in this directory are derived from the GeoNames geographical
database, downloaded from https://download.geonames.org/export/dump/.

GeoNames data is licensed under the Creative Commons Attribution 4.0 License:
https://creativecommons.org/licenses/by/4.0/

`manifest.json` records the source archives and their SHA-256 checksums. The
worldwide snapshot uses `cities15000`; Germany uses `cities500` for broader
coverage. Runtime code uses only these vendored files and makes no network calls.
