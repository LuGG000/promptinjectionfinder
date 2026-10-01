#!/usr/bin/env sh
# PromptInjectionFinder - startet die Offline-Oberflaeche
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
if ! $PY -c "import pymupdf, numpy" >/dev/null 2>&1; then
  echo "Installiere Abhaengigkeiten (einmalig, benoetigt Internet)..."
  $PY -m pip install -r requirements.txt || exit 1
fi
exec $PY -m pif gui "$@"
