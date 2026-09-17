#!/bin/bash
# Compatible with the Bash 3.2 shipped with macOS.
set -euo pipefail

PROSPERO_ROOT="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$PROSPERO_ROOT"

fail() { printf 'Setup failed: %s\n' "$*" >&2; exit 1; }
trap 'printf "Setup failed. Fix the error above, then rerun bash install.sh.\n" >&2' ERR

usage() {
    printf '%s\n' "Prospero's Study - macOS dependency setup" \
        'Usage: bash install.sh [--check-only]' \
        'Installs missing Python/Node through an existing Homebrew installation.' \
        '--check-only verifies an existing installation without installing or building.'
}

find_brew() {
    local candidate
    for candidate in "$(command -v brew || true)" /opt/homebrew/bin/brew /usr/local/bin/brew; do
        if [[ -n "$candidate" && -x "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

add_brew_paths() {
    [[ -n "$PROSPERO_BREW" ]] || return 0
    local prefix
    prefix="$("$PROSPERO_BREW" --prefix)"
    export PATH="$PATH:$prefix/opt/python@3.12/bin:$prefix/opt/node@24/bin:$prefix/opt/node@22/bin:$prefix/bin"
}

valid_python() {
    [[ -n "$1" && -x "$1" ]] || return 1
    "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' >/dev/null 2>&1
}

find_python() {
    local candidate prefix=''
    if [[ -n "$PROSPERO_BREW" ]]; then prefix="$("$PROSPERO_BREW" --prefix)"; fi
    for candidate in "$PROSPERO_ROOT/.venv/bin/python" "$(command -v python3.12 || true)" "$(command -v python3 || true)" "$prefix/bin/python3.12"; do
        if valid_python "$candidate"; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

valid_node() {
    [[ -n "$1" && -x "$1" ]] || return 1
    "$1" -e 'const [major, minor] = process.versions.node.split(".").map(Number); process.exit(major > 22 || (major === 22 && minor >= 12) ? 0 : 1)' >/dev/null 2>&1
}

find_node() {
    local candidate prefix=''
    if [[ -n "$PROSPERO_BREW" ]]; then prefix="$("$PROSPERO_BREW" --prefix)"; fi
    candidate="$(command -v node || true)"
    if valid_node "$candidate"; then printf '%s\n' "$candidate"; return 0; fi
    [[ -n "$prefix" ]] || return 1
    for candidate in "$prefix/opt/node@24/bin/node" "$prefix/opt/node@22/bin/node"; do
        if valid_node "$candidate"; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

install_missing_runtimes() {
    [[ -n "$PROSPERO_PYTHON" && -n "$PROSPERO_NODE" ]] && return 0
    [[ "$PROSPERO_CHECK_ONLY" == 0 ]] || fail 'Python 3.12+ and Node.js 22.12+ are required. Run bash install.sh first.'
    [[ -n "$PROSPERO_BREW" ]] || fail 'Install Homebrew from https://brew.sh and rerun this script, or install Python 3.12+ and Node.js 22.12+ manually.'
    set --
    if [[ -z "$PROSPERO_PYTHON" ]]; then set -- "$@" python@3.12; fi
    if [[ -z "$PROSPERO_NODE" ]]; then set -- "$@" node@24; fi
    printf 'Installing missing runtimes with Homebrew: %s\n' "$*"
    "$PROSPERO_BREW" install "$@"
    hash -r
    PROSPERO_PYTHON="$(find_python || true)"
    PROSPERO_NODE="$(find_node || true)"
}

check_installation() {
    local python="$PROSPERO_ROOT/.venv/bin/python"
    valid_python "$python" || fail 'The project environment is missing or incompatible. Run bash install.sh first.'
    "$python" -m pip check
    "$python" -B -c 'import fastapi, uvicorn, httpx, pydantic, keyring, PIL'
    "$PROSPERO_NPM" ls --depth=0
    [[ -f "$PROSPERO_ROOT/dist/index.html" ]] || fail 'The interface has not been built. Run bash install.sh.'
}

PROSPERO_CHECK_ONLY=0
for argument in "$@"; do
    case "$argument" in
        --check-only) PROSPERO_CHECK_ONLY=1 ;;
        --help|-h) usage; exit 0 ;;
        *) fail "Unknown option: $argument. Use --help for usage." ;;
    esac
done
[[ "$(uname -s)" == Darwin ]] || fail 'This installer is for macOS. On Windows, use install.bat.'

if [[ -e .venv || -L .venv ]]; then
    valid_python "$PROSPERO_ROOT/.venv/bin/python" || fail 'The existing .venv is incompatible (possibly copied from Windows). Rename it and rerun this script. Your data folder is separate and will not be changed.'
fi

printf "%s\n" "Prospero's Study - dependency setup"
PROSPERO_BREW="$(find_brew || true)"
add_brew_paths
PROSPERO_PYTHON="$(find_python || true)"
PROSPERO_NODE="$(find_node || true)"
install_missing_runtimes
[[ -n "$PROSPERO_PYTHON" ]] || fail 'Python 3.12+ was not found after setup. Check its installation and retry.'
[[ -n "$PROSPERO_NODE" ]] || fail 'Node.js 22.12+ was not found after setup. Check its installation and retry.'
PROSPERO_NODE_DIR="$(dirname "$PROSPERO_NODE")"
export PATH="$PROSPERO_NODE_DIR:$PATH"
PROSPERO_NPM="$PROSPERO_NODE_DIR/npm"
[[ -x "$PROSPERO_NPM" ]] || fail 'npm is missing beside Node.js. Repair the Node.js installation and rerun this script.'

if [[ "$PROSPERO_CHECK_ONLY" == 0 ]]; then
    if [[ ! -d .venv ]]; then "$PROSPERO_PYTHON" -m venv "$PROSPERO_ROOT/.venv"; fi
    "$PROSPERO_ROOT/.venv/bin/python" -m pip install --disable-pip-version-check --no-input -r requirements.lock.txt
    "$PROSPERO_NPM" ci --no-audit --no-fund
    "$PROSPERO_NPM" run build
fi
check_installation
printf '%s\n' 'Ready. Run bash launch.sh to open the interface.' \
    'Model accounts and optional local model servers are configured separately in Settings.'
