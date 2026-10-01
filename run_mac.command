#!/usr/bin/env sh
# macOS: double-click in Finder starts PromptInjectionFinder in Terminal.
cd "$(dirname "$0")"
exec sh ./run_linux_mac.sh "$@"
