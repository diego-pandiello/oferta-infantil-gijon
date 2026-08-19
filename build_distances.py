#!/usr/bin/env python3
"""Geocode each localidad in the oferta and route it from Gijón by car.

Two public services, no API key:
  * Nominatim (OpenStreetMap) for geocoding, rate limited to 1 request/second.
  * OSRM demo server for car routing.

Results are cached in data/geo_cache.json, so re-running is cheap and only
looks up localidades it has not seen before.

Usage:
    python3 build_distances.py                 # only new localidades
    python3 build_distances.py --refresh SOMIO  # force one localidad again
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

NOMINATIM = "https://nominatim.openstreetmap.org/search"
OSRM = "https://router.project-osrm.org/route/v1/driving"
USER_AGENT = "oferta-infantil-gijon/1.0 (personal job-search tool)"

# Gijón city centre, the origin for every route.
ORIGIN = {"name": "Gijón", "lat": 43.5322, "lon": -5.6611}

# Asturias bounding box, to keep Nominatim from matching same-named places
# elsewhere in Spain. Order is left,top,right,bottom.
ASTURIAS_VIEWBOX = "-7.20,43.70,-4.45,42.85"

CACHE_PATH = Path("data/geo_cache.json")
PLAZAS_PATH = Path("data/plazas.json")
OUTPUT_PATH = Path("data/distances.json")

# Localidades Nominatim cannot resolve from the oferta's spelling alone.
# Keyed by the oferta's "CONCEJO|LOCALIDAD", valued with a better query.
QUERY_OVERRIDES = {}


def http_get_json(url, params):
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{url}?{query}", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def geocode(concejo, localidad):
    """Return (lat, lon, display_name) for a localidad, or None."""
    key = f"{concejo}|{localidad}"
    candidates = []
    if key in QUERY_OVERRIDES:
        candidates.append(QUERY_OVERRIDES[key])
    if localidad != concejo:
        candidates.append(f"{localidad}, {concejo}, Asturias, España")
    candidates.append(f"{localidad}, Asturias, España")
    if localidad != concejo:
        candidates.append(f"{concejo}, Asturias, España")

    for query in candidates:
        try:
            results = http_get_json(
                NOMINATIM,
                {
                    "q": query,
                    "format": "json",
                    "limit": 1,
                    "countrycodes": "es",
                    "viewbox": ASTURIAS_VIEWBOX,
                    "bounded": 1,
                },
            )
        except urllib.error.URLError as exc:
            print(f"    geocode error for {query!r}: {exc}", file=sys.stderr)
            time.sleep(2)
            continue
        time.sleep(1.1)  # Nominatim asks for at most 1 request per second
        if results:
            hit = results[0]
            return float(hit["lat"]), float(hit["lon"]), hit.get("display_name", query)
    return None


def route_by_car(lat, lon):
    """Return (km, minutes) driving from ORIGIN, or None."""
    coords = f"{ORIGIN['lon']},{ORIGIN['lat']};{lon},{lat}"
    try:
        payload = http_get_json(f"{OSRM}/{coords}", {"overview": "false"})
    except urllib.error.URLError as exc:
        print(f"    routing error: {exc}", file=sys.stderr)
        return None
    if payload.get("code") != "Ok" or not payload.get("routes"):
        return None
    route = payload["routes"][0]
    return round(route["distance"] / 1000, 1), round(route["duration"] / 60)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--refresh",
        action="append",
        default=[],
        help="localidad name to look up again even if cached (repeatable)",
    )
    args = ap.parse_args()
    refresh = {name.upper() for name in args.refresh}

    plazas = json.loads(PLAZAS_PATH.read_text(encoding="utf-8"))["plazas"]
    places = sorted({(p["concejo"], p["localidad"]) for p in plazas})

    cache = {}
    if CACHE_PATH.exists():
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))

    todo = [
        (concejo, localidad)
        for concejo, localidad in places
        if f"{concejo}|{localidad}" not in cache or localidad.upper() in refresh
    ]
    print(
        f"{len(places)} localidades, {len(cache)} cached, {len(todo)} to fetch",
        file=sys.stderr,
    )

    for index, (concejo, localidad) in enumerate(todo, start=1):
        key = f"{concejo}|{localidad}"
        print(f"[{index}/{len(todo)}] {localidad} ({concejo})", file=sys.stderr)
        located = geocode(concejo, localidad)
        if not located:
            cache[key] = {"concejo": concejo, "localidad": localidad, "error": "geocode"}
            continue
        lat, lon, display = located
        routed = route_by_car(lat, lon)
        entry = {
            "concejo": concejo,
            "localidad": localidad,
            "lat": lat,
            "lon": lon,
            "display_name": display,
        }
        if routed:
            entry["km"], entry["minutes"] = routed
        else:
            entry["error"] = "route"
        cache[key] = entry
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    OUTPUT_PATH.write_text(
        json.dumps(
            {"origin": ORIGIN, "places": cache}, ensure_ascii=False, indent=1
        ),
        encoding="utf-8",
    )

    failed = [v for v in cache.values() if "error" in v]
    print(f"\ngeocoded+routed: {len(cache) - len(failed)}", file=sys.stderr)
    print(f"failed:          {len(failed)}", file=sys.stderr)
    for entry in failed:
        print(
            f"  ! {entry['localidad']} ({entry['concejo']}): {entry['error']}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
