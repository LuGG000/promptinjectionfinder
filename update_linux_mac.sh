#!/usr/bin/env sh
# PromptInjectionFinder – update to the newest release (Linux / macOS)
# run_linux_mac.sh in command line mode also repairs .venv first when needed.
PIF_LAUNCH=cli exec sh "$(dirname "$0")/run_linux_mac.sh" update "$@"
