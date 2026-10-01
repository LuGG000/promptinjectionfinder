#!/usr/bin/env sh
# macOS: Doppelklick im Finder startet PromptInjectionFinder im Terminal.
cd "$(dirname "$0")"
exec sh ./run_linux_mac.sh "$@"
