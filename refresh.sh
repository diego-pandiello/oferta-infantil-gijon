#!/usr/bin/env bash
# Rebuild the site from a new oferta PDF.
#
#   ./refresh.sh ~/Downloads/2026-09-....pdf
#
# Geocoding is cached in data/geo_cache.json, so only localidades that have never
# been seen before hit the network. Commit and push afterwards to deploy.

set -euo pipefail
cd "$(dirname "$0")"

if [ $# -ne 1 ]; then
  echo "usage: $0 <oferta.pdf>" >&2
  exit 64
fi

PDF="$1"
[ -f "$PDF" ] || { echo "no such file: $PDF" >&2; exit 66; }
command -v pdftotext >/dev/null || { echo "need pdftotext (brew install poppler)" >&2; exit 69; }

echo "==> parsing $(basename "$PDF")"
python3 parse_oferta.py "$PDF"

echo "==> geocoding and routing from Gijón"
python3 build_distances.py

echo "==> building docs/data.js"
python3 build_app.py

if command -v node >/dev/null; then
  echo "==> testing"
  node test_app.js | tail -1
else
  echo "==> skipping tests (node not installed)" >&2
fi

echo
echo "Done. Review, then deploy with:"
echo "  git add -A && git commit -m 'chore: oferta de \$(date +%Y-%m-%d)' && git push"
