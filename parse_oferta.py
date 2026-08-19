#!/usr/bin/env python3
"""Parse the Asturias "OFERTA DE PLAZAS" PDF into structured JSON.

Usage:
    python3 parse_oferta.py <oferta.pdf|oferta.txt> [-o data/plazas.json]

The PDF is a fixed-width report. Its shape, per centre:

    CONCEJO                        LOCALIDAD
    33000017      Colegio Publico de Berducedo
    Codigo        Especialidad                      Iti Jornada Funcion
    772552 V      0597 032 LENGUA EXTRANJERA: INGLES  N    J      2
             Por centro hay   2 especialidades y   2  vacantes totales

The column between "Codigo" and the especialidad code is unlabelled in the
report header; "V" marks a vacante and the two-letter codes mark other plaza
types. Some rows carry a trailing 7-digit code, which is a second especialidad
attached to the same plaza.
"""

import argparse
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

# 33000017     Colegio Publico de Berducedo
CENTRE_RE = re.compile(r"^\s{2,}(\d{8})\s{2,}(\S.*?)\s*$")

# 772552 V      0597 032 LENGUA EXTRANJERA: INGLES     N    J    2
PLAZA_RE = re.compile(
    r"""^\s+(?P<codigo>\d{6})\s+          # plaza code
         (?P<tipo>[A-Z]{1,2})?\s+         # V = vacante, or a 2-letter type code
         (?P<cuerpo>\d{4})\s              # 0590 secondary, 0597 primary/infant
         (?P<especialidad>\d{3})\s        # especialidad within the cuerpo
         (?P<nombre>.*?)\s{2,}            # especialidad name
         (?P<iti>[SN])                    # itinerante
         (?P<rest>.*)$                    # jornada, funcion, extra especialidad
      """,
    re.VERBOSE,
)

# "Por centro hay  2 especialidades y  2  vacantes totales"
TOTALS_RE = re.compile(
    r"Por centro hay\s+(\d+)\s+especialidades y\s+(\d+)\s+vacantes totales"
)

# The report stamps its own date in each page header, e.g. "18-AGO-26".
STAMP_RE = re.compile(r"\b(\d{1,2})-([A-Z]{3})-(\d{2})\b")
MONTHS = {
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12,
}
PAGES_RE = re.compile(r"P.gina \d+ de (\d+)")

# Lines that are page furniture, never data.
NOISE_RE = re.compile(
    r"Gobierno del Principado|CONSEJER|OFERTA DE PLAZAS|"
    r"^\s*C.digo\s+Especialidad|Funci.n Biling.e|P.gina \d+ de \d+|"
    r"^\s*\d{1,2}-[A-Z]{3}-\d{2}\s*$"
)

# A concejo/localidad header: two all-caps blocks separated by a wide gap, or a
# single all-caps block when concejo and localidad coincide.
HEADER_RE = re.compile(
    r"^\s{2,}(?P<concejo>[A-ZÁÉÍÓÚÑÜ0-9][A-ZÁÉÍÓÚÑÜ0-9 .,'\"()/-]*?)"
    r"(?:\s{3,}(?P<localidad>[A-ZÁÉÍÓÚÑÜ0-9][A-ZÁÉÍÓÚÑÜ0-9 .,'\"()/-]*?))?\s*$"
)


def strip_accents(text):
    """Fold accents so 'GIJÓN' and 'GIJON' compare equal."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def extract_text(source):
    """Return the report text, running pdftotext if given a PDF."""
    path = Path(source)
    if path.suffix.lower() != ".pdf":
        return path.read_text(encoding="utf-8")
    result = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def parse_rest(rest):
    """Split the tail after the Iti column into jornada, funcion and extra code.

    The tail holds up to three space-separated tokens: jornada (H or J), the
    bilingual funcion digit (1-4), and a 7-digit second especialidad code.
    """
    jornada = funcion = extra = None
    for token in rest.split():
        if token in ("H", "J"):
            jornada = token
        elif len(token) == 1 and token.isdigit():
            funcion = token
        elif len(token) == 7 and token.isdigit():
            extra = f"{token[:4]} {token[4:]}"
        else:
            return jornada, funcion, extra, token  # unrecognised
    return jornada, funcion, extra, None


def source_metadata(text):
    """Pull the report's own date stamp and page count out of the page furniture.

    Read from the document rather than hardcoded, so the app's "datos de" banner
    is always the vintage of the PDF that was actually parsed.
    """
    meta = {"source_date": None, "source_date_label": None, "pages": None}

    stamp = STAMP_RE.search(text)
    if stamp:
        day, month_abbr, year = stamp.groups()
        month = MONTHS.get(month_abbr)
        if month:
            meta["source_date"] = f"20{year}-{month:02d}-{int(day):02d}"
            meta["source_date_label"] = f"{int(day)}-{month_abbr}-{year}"

    pages = PAGES_RE.search(text)
    if pages:
        meta["pages"] = int(pages.group(1))

    return meta


def parse(text):
    """Parse the report text into (plazas, centre_totals, warnings)."""
    plazas = []
    totals = []
    warnings = []

    concejo = localidad = None
    centre_code = centre_name = None
    centre_rows = 0

    # Drop blanks and page furniture up front, so "the next meaningful line"
    # is a straightforward lookahead.
    lines = [
        (lineno, raw.rstrip())
        for lineno, raw in enumerate(text.splitlines(), start=1)
        if raw.strip() and not NOISE_RE.search(raw)
    ]

    for index, (lineno, line) in enumerate(lines):
        totals_match = TOTALS_RE.search(line)
        if totals_match:
            totals.append(
                {
                    "centre_code": centre_code,
                    "declared_especialidades": int(totals_match.group(1)),
                    "declared_vacantes": int(totals_match.group(2)),
                    "parsed_rows": centre_rows,
                }
            )
            centre_rows = 0
            continue

        plaza_match = PLAZA_RE.match(line)
        if plaza_match:
            if centre_code is None:
                warnings.append(f"line {lineno}: plaza before any centre: {line!r}")
                continue
            group = plaza_match.groupdict()
            jornada, funcion, extra, unknown = parse_rest(group["rest"])
            if unknown:
                warnings.append(f"line {lineno}: unparsed token {unknown!r}: {line!r}")
            plazas.append(
                {
                    "codigo": group["codigo"],
                    "tipo": group["tipo"] or "",
                    "vacante": group["tipo"] == "V",
                    "cuerpo": group["cuerpo"],
                    "especialidad": group["especialidad"],
                    "nombre": " ".join(group["nombre"].split()),
                    "itinerante": group["iti"] == "S",
                    "jornada": jornada,
                    "funcion_bilingue": funcion,
                    "especialidad_extra": extra,
                    "concejo": concejo,
                    "localidad": localidad,
                    "centre_code": centre_code,
                    "centre_name": centre_name,
                }
            )
            centre_rows += 1
            continue

        centre_match = CENTRE_RE.match(line)
        if centre_match:
            centre_code, centre_name = centre_match.group(1), centre_match.group(2)
            centre_rows = 0
            continue

        # A concejo/localidad header always introduces a centre, so the next
        # meaningful line must be the centre-code line. Without this check, a
        # wrapped especialidad name ("...MANTENIMIENTO DE / VEHICULOS") looks
        # exactly like a header and would silently relocate every plaza after it.
        next_line = lines[index + 1][1] if index + 1 < len(lines) else ""
        header_match = HEADER_RE.match(line)
        folded = strip_accents(line.strip())
        if (
            header_match
            and CENTRE_RE.match(next_line)
            and folded == folded.upper()
            and any(c.isalpha() for c in folded)
        ):
            concejo = " ".join(header_match.group("concejo").split())
            loc = header_match.group("localidad")
            localidad = " ".join(loc.split()) if loc else concejo
            continue

        # Otherwise an all-caps orphan line is the tail of the previous plaza's
        # especialidad name, wrapped by the report's column width.
        if plazas and folded == folded.upper() and any(c.isalpha() for c in folded):
            plazas[-1]["nombre"] += " " + " ".join(line.split())
            continue

        warnings.append(f"line {lineno}: unrecognised: {line!r}")

    return plazas, totals, warnings


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", help="oferta PDF or pre-extracted .txt")
    ap.add_argument("-o", "--output", default="data/plazas.json")
    args = ap.parse_args()

    text = extract_text(args.source)
    plazas, totals, warnings = parse(text)
    meta = source_metadata(text)
    meta["source_file"] = Path(args.source).name
    meta["plazas"] = len(plazas)
    meta["centres"] = len(totals)

    # The PDF's "vacantes totales" is a row count, so it is the figure to check
    # against. "especialidades" is a distinct count and will legitimately differ.
    # Per-centre counts reset at a page break, so the grand total is the reliable
    # check; per-centre differences are only flagged as hints.
    declared_total = sum(t["declared_vacantes"] for t in totals)
    per_centre_diffs = [
        t for t in totals if t["parsed_rows"] != t["declared_vacantes"]
    ]

    print(f"source date:          {meta['source_date_label']} ({meta['pages']} pages)", file=sys.stderr)
    print(f"plazas parsed:        {len(plazas)}", file=sys.stderr)
    print(f"centres:              {len(totals)}", file=sys.stderr)
    print(f"declared vacantes:    {declared_total}", file=sys.stderr)
    print(
        f"total check:          {'OK' if declared_total == len(plazas) else 'MISMATCH'}",
        file=sys.stderr,
    )
    print(f"duplicate codigos:    {len(plazas) - len({p['codigo'] for p in plazas})}", file=sys.stderr)
    print(f"warnings:             {len(warnings)}", file=sys.stderr)
    print(
        f"per-centre diffs:     {len(per_centre_diffs)} (expected for centres split across pages)",
        file=sys.stderr,
    )
    for warning in warnings[:20]:
        print(f"  ! {warning}", file=sys.stderr)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        json.dumps({"meta": meta, "plazas": plazas}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"wrote {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
