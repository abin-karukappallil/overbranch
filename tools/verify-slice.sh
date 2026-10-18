#!/usr/bin/env bash
# tools/verify-slice.sh — the gate a plan slice must pass.
#
#   tools/verify-slice.sh [spec ...]
#
# With no arguments it runs the whole suite. With arguments it runs the
# frontend typecheck plus only the named specs:
#
#   *.py   -> pytest, from backend/
#   *.mjs  -> bundled with the esbuild in node_modules, then run under node
#
# ESLint is deliberately not run: it is broken in this repo (see CLAUDE.md).
# Two backend test failures are pre-existing and expected; this script reports
# them but a caller comparing against the baseline should not treat them as new.
set -uo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"
FAIL=0

# The backend's dependencies live in backend/.venv, not in the system python,
# so a bare `python -m pytest` fails at import with ModuleNotFoundError.
if [ -x "$ROOT/backend/.venv/bin/python" ]; then
  PY="$ROOT/backend/.venv/bin/python"
else
  PY="$(command -v python3 || command -v python)"
  echo "   (warning: backend/.venv not found; falling back to $PY)"
fi
declare -a RESULTS=()

record() { # record <name> <rc>
  if [ "$2" -eq 0 ]; then
    RESULTS+=("PASS  $1")
  else
    RESULTS+=("FAIL  $1")
    FAIL=1
  fi
}

echo "── typecheck (tsc --noEmit)"
npx --yes tsc --noEmit
record "typecheck" $?

PY_SPECS=()
MJS_SPECS=()
for arg in "$@"; do
  case "$arg" in
    *.py)  PY_SPECS+=("$arg") ;;
    *.mjs) MJS_SPECS+=("$arg") ;;
    *)     echo "   (ignoring non-spec argument: $arg)" ;;
  esac
done

if [ $# -eq 0 ]; then
  echo "── pytest (full backend suite)"
  ( cd backend && "$PY" -m pytest -q )
  record "pytest (all)" $?

  echo "── client-side checks"
  bash scripts/run-collab-tests.sh
  record "run-collab-tests.sh" $?
else
  if [ ${#PY_SPECS[@]} -gt 0 ]; then
    REL=()
    for p in "${PY_SPECS[@]}"; do REL+=("${p#backend/}"); done
    echo "── pytest ${REL[*]}"
    ( cd backend && "$PY" -m pytest -q "${REL[@]}" )
    record "pytest ${REL[*]}" $?
  fi
  if [ ${#MJS_SPECS[@]} -gt 0 ]; then
    OUT="$(mktemp -d)"
    trap 'rm -rf "$OUT"' EXIT
    for entry in "${MJS_SPECS[@]}"; do
      echo "── $entry"
      "$ROOT/node_modules/esbuild/bin/esbuild" "$entry" \
        --bundle --platform=node --format=esm --log-level=warning \
        --outfile="$OUT/$(basename "$entry")" \
        && node "$OUT/$(basename "$entry")"
      record "$entry" $?
    done
  fi
fi

echo
echo "──────── verify-slice summary ────────"
printf '%s\n' "${RESULTS[@]}"
exit $FAIL
