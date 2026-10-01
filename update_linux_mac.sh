#!/usr/bin/env sh
# PromptInjectionFinder – auf die neueste Release-Version aktualisieren (Linux / macOS)
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Noch nicht eingerichtet. Bitte zuerst ./run_linux_mac.sh starten."
  exit 1
fi
exec .venv/bin/python -m pif update "$@"
