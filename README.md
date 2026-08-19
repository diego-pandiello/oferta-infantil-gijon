# Oferta de plazas 2026/2027 — Educación Infantil cerca de Gijón

Turns the Asturias `OFERTA DE PLAZAS` PDF into a filterable static site, so you can find
Educación Infantil plazas ranked by **driving time from Gijón**, and filter by vacante (V),
itinerante (Iti) and jornada (H / J).

> **Herramienta no oficial.** Not affiliated with the Consejería de Educación del
> Principado de Asturias. The only valid source is the official convocatoria —
> [Educastur · convocatoria y adjudicación](https://www.educastur.es/profesorado/funcion-publica-interina/convocatoria-adjudicacion).
> Always check the original PDF before applying for a plaza.

## Quick start

```bash
brew install poppler                              # provides pdftotext
./refresh.sh ~/Downloads/<oferta>.pdf             # parse → geocode → build → test
open docs/index.html
```

`refresh.sh` runs the whole pipeline. Only step 2 touches the network, and it caches into
`data/geo_cache.json`, so a later PDF only looks up localidades never seen before. No
Python dependencies.

## Pipeline

| File | Does |
|---|---|
| `parse_oferta.py` | `pdftotext -layout` → one JSON record per plaza, plus the PDF's own date stamp. Validates its row count against the PDF's per-centre "vacantes totales". |
| `build_distances.py` | Nominatim geocode + OSRM car routing from Gijón, per distinct localidad. Cached. |
| `build_app.py` | Joins plazas with distances → `docs/data.js`. |
| `docs/index.html` | The whole app: filters, sortable table, CSV export, per-row Google Maps route link. No dependencies, no network calls. |
| `test_app.js` | `node test_app.js` — runs the app's real script against a DOM stub and drives every filter, sort, the vintage banner and the CSV export. 33 checks. |

## Hosting

`docs/` is a self-contained static site — 16 KB of HTML plus a 1.3 MB `data.js` that gzips
to **51 KB**, so the whole thing is ~56 KB over the wire. It works on any static host, and
directly from `file://`.

It is published with **GitHub Pages** serving `docs/` from `main`. Deploying an update is
`./refresh.sh <new.pdf>` followed by a commit and push.

## Filters

- **Especialidad** — defaults to `0597 031 EDUCACIÓN INFANTIL`; every especialidad in the
  PDF is selectable, so the same app works if you widen the search.
- **Tiempo en coche máx.** — slider 5–150 min; the top position means no limit. Colour
  coding in the Min column: green ≤30, amber ≤60, red >60.
- **Vacante (V)** — todas / sólo V / sin V.
- **Itinerante (Iti)** — todas / no (N) / sí (S).
- **Jornada** — todas / completa (blank in the PDF) / J / H.
- **Free text** over centre, localidad and concejo.

## Reading the columns

Straight from the PDF:

- **V** in the unlabelled column after `Código` marks a *vacante*. Other values appear
  there too — `JA`, `KA`, `HA`, `IA`, `Z`, or blank — which are other plaza types.
- **Iti** — `S` itinerante, `N` not.
- **Función** — `1` francés, `2` inglés, `3` alemán, `4` italiano (bilingüe). This legend
  is printed in the PDF footer.

Not in the PDF, taken from ANPE Asturias / interino guides — **verify in the convocatoria
before relying on it**:

- **Jornada** blank = jornada completa, `J` = media jornada, `H` = media jornada por
  horas (10 h).

## Caveats worth knowing

- **The data has a vintage.** The site shows the PDF's own date stamp, and warns once it
  is more than 30 days old. The oferta is republished regularly; a stale copy is worse
  than no copy.
- **Distances are to the centre of the localidad, not to the school building.** For a
  `C.R.A.` (Colegio Rural Agrupado) the classrooms are spread across several villages, so
  the real commute can differ substantially. Use the `mapa` link to check the real route.
- Consequently **all 50 plazas inside Gijón show the same 4 min / 2.4 km** — the whole
  concejo collapses to one point. Sort or search by centre name to tell them apart.
- Driving times come from OSRM's free demo server with default car settings — no traffic,
  no time of day.
- Origin is Gijón city centre (43.5322, -5.6611). Change `ORIGIN` in `build_distances.py`
  and re-run to route from a different address.
- Plazas whose localidad could not be geocoded are **never hidden** by the time filter —
  they show `?` in the Min column and are listed at the foot of the page.

## Parse confidence

For the 18-AGO-26 PDF (140 pages):

- 3,293 plazas across 391 centres, 0 unrecognised lines, 0 duplicate plaza codes.
- Parsed row count equals the sum of the PDF's own declared "vacantes totales" (3,293).
- All 151 localidades geocoded and routed; 0 rows without a distance.
- 303 plazas are `0597 031 EDUCACIÓN INFANTIL`, in 207 centres and 117 localidades.

`per-centre diffs: 2` in the parser output is expected: the per-centre counter restarts
when a centre's listing is split across a page break. The grand total is the real check.

## Licence

Code: MIT. The underlying plaza data is public sector information published by the
Consejería de Educación del Principado de Asturias.
