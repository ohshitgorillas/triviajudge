#!/bin/sh
# Run one gate module from the plugin checkout, without requiring an install.
# The package is pure standard library, so the checkout itself is the import path.
# Each gate has one hook mode, and the caller names the gate, not the flag.
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: run-gate.sh <md_trivia|comment_trivia|archaeology>" >&2
    exit 1
fi

case "$1" in
    md_trivia | comment_trivia) mode="--stop" ;;
    archaeology) mode="--post-tool-use" ;;
    *)
        echo "usage: run-gate.sh <md_trivia|comment_trivia|archaeology>" >&2
        exit 1
        ;;
esac

root="${CLAUDE_PLUGIN_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"

if [ -n "${PYTHONPATH:-}" ]; then
    PYTHONPATH="$root:$PYTHONPATH"
else
    PYTHONPATH="$root"
fi
export PYTHONPATH

# The package needs 3.12. Without this check the failure is an import-time
# SyntaxError or a bare `command not found`, which reads as a broken plugin
# rather than an old interpreter.
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
    found=$(python3 -V 2>&1) || found="no python3 on PATH"
    echo "triviajudge: needs Python 3.12 or newer on PATH as python3; found: $found" >&2
    exit 1
fi

exec python3 -m "triviajudge.$1" "$mode"
