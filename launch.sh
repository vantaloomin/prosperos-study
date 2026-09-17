#!/bin/bash
# exec keeps the app in this terminal and passes Ctrl+C to the shared launcher.
set -euo pipefail

PROSPERO_ROOT="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$PROSPERO_ROOT"

fail() { printf 'Launch failed: %s\n' "$*" >&2; exit 1; }
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
    printf '%s\n' "Prospero's Study - macOS launcher" \
        'Usage: bash launch.sh [--no-browser] [--port 8765]' \
        'Keep this terminal open. Press Ctrl+C to stop the app.'
    exit 0
fi
[[ "$(uname -s)" == Darwin ]] || fail 'This launcher is for macOS. On Windows, use launch.bat.'
PROSPERO_PYTHON="$PROSPERO_ROOT/.venv/bin/python"
[[ -x "$PROSPERO_PYTHON" ]] || fail 'Dependencies are missing. Run bash install.sh first.'
"$PROSPERO_PYTHON" -B -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' || fail 'Python 3.12+ is required. Run bash install.sh.'
"$PROSPERO_PYTHON" -B -c 'import fastapi, uvicorn, httpx, pydantic, keyring, PIL' || fail 'Dependencies are incomplete. Run bash install.sh.'
[[ -f "$PROSPERO_ROOT/dist/index.html" ]] || fail 'The interface is not built. Run bash install.sh first.'
exec "$PROSPERO_PYTHON" -m scripts.launch_interface "$@"
