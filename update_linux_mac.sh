#!/usr/bin/env sh
# PromptInjectionFinder – update to the newest release (Linux / macOS)
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Not set up yet. Please start ./run_linux_mac.sh first."
  exit 1
fi
exec .venv/bin/python -m pif update "$@"
