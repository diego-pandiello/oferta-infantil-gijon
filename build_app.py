#!/usr/bin/env python3
"""Join parsed plazas with driving distances and emit the app's data file.

Usage:
    python3 build_app.py            # writes docs/data.js
"""

import json
from pathlib import Path

PLAZAS_PATH = Path("data/plazas.json")
DISTANCES_PATH = Path("data/distances.json")
OUTPUT_PATH = Path("docs/data.js")

# Fields the app actually renders, in a compact order.
FIELDS = [
    "codigo",
    "tipo",
    "vacante",
    "cuerpo",
    "especialidad",
    "nombre",
    "itinerante",
    "jornada",
    "funcion_bilingue",
    "especialidad_extra",
    "concejo",
    "localidad",
    "centre_code",
    "centre_name",
]


def main():
    parsed = json.loads(PLAZAS_PATH.read_text(encoding="utf-8"))
    plazas, meta = parsed["plazas"], parsed["meta"]
    distances = json.loads(DISTANCES_PATH.read_text(encoding="utf-8"))
    places = distances["places"]

    rows = []
    unlocated = set()
    for plaza in plazas:
        row = {field: plaza[field] for field in FIELDS}
        place = places.get(f"{plaza['concejo']}|{plaza['localidad']}", {})
        row["km"] = place.get("km")
        row["minutes"] = place.get("minutes")
        row["lat"] = place.get("lat")
        row["lon"] = place.get("lon")
        if row["minutes"] is None:
            unlocated.add((plaza["concejo"], plaza["localidad"]))
        rows.append(row)

    # Especialidad list for the dropdown, most plazas first.
    counts = {}
    for row in rows:
        key = (row["cuerpo"], row["especialidad"], row["nombre"])
        counts[key] = counts.get(key, 0) + 1
    especialidades = [
        {"cuerpo": c, "especialidad": e, "nombre": n, "count": count}
        for (c, e, n), count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    payload = {
        "meta": meta,
        "origin": distances["origin"],
        "rows": rows,
        "especialidades": especialidades,
        "unlocated": sorted(f"{loc} ({con})" for con, loc in unlocated),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        "window.OFERTA = " + json.dumps(payload, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )

    infantil = [r for r in rows if r["cuerpo"] == "0597" and r["especialidad"] == "031"]
    print(f"rows:              {len(rows)}")
    print(f"educación infantil {len(infantil)}")
    print(f"without distance:  {sum(1 for r in rows if r['minutes'] is None)}")
    print(f"unlocated places:  {len(unlocated)}")
    for name in payload["unlocated"]:
        print(f"  ! {name}")
    print(f"wrote {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
