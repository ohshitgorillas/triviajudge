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

exec python3 -m "triviajudge.$1" "$mode"
