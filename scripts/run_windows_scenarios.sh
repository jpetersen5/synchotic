#!/usr/bin/env bash
# Run scripts/scenarios.py on a Windows host over ssh: the real app in a ConPTY,
# against real Drive, one scenario at a time.
#
#   scripts/run_windows_scenarios.sh winprox                 every scenario
#   scripts/run_windows_scenarios.sh winprox first_sync      the named ones
#   scripts/run_windows_scenarios.sh winprox --app           the built exe (see --exe in run_windows_check.sh)
#
# Syncs this worktree to %USERPROFILE%\synchotic-validate\src and signs in with
# this Mac's BYOC token, as run_windows_check.sh does. Screens, app logs and
# steps come back to runs/windows/<scenario>/.
set -euo pipefail

HOST="${1:?usage: run_windows_scenarios.sh <ssh-host> [--app] [scenario ...]}"
shift
APP=0
if [ "${1:-}" = "--app" ]; then APP=1; shift; fi
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUTH="$HOME/Library/Application Support/Synchotic"

KEY="${GOOGLE_API_KEY:-}"
if [ -z "$KEY" ]; then
  for f in "$REPO/.env" "$(git -C "$REPO" rev-parse --path-format=absolute --git-common-dir)/../.env"; do
    [ -f "$f" ] && KEY="$(grep -E '^GOOGLE_API_KEY=' "$f" | head -1 | cut -d= -f2-)" && break
  done
fi
[ -n "$KEY" ] || { echo "no GOOGLE_API_KEY in env or .env"; exit 2; }

PROFILE="$(ssh "$HOST" 'echo %USERPROFILE%' | tr -d '\r')"
DEST="$PROFILE\\synchotic-validate"
FWD="${DEST//\\//}"

echo "==> syncing $REPO -> $HOST:$DEST\\src"
ssh "$HOST" "(if exist \"$DEST\\src\" rmdir /s /q \"$DEST\\src\") & mkdir \"$DEST\\src\" \"$DEST\\auth\" 2>nul & echo ok" >/dev/null
COPYFILE_DISABLE=1 tar czf - -C "$REPO" \
  --exclude .git --exclude .venv --exclude venv --exclude .env --exclude dist --exclude build \
  --exclude .dm-sync --exclude "Sync Charts" --exclude __pycache__ --exclude .pytest_cache \
  --exclude .overlap_cache.json --exclude libs --exclude runs . \
  | ssh "$HOST" "tar xzf - -C \"$FWD/src\""

# Releases a scenario launches (`launch v1.5.6`): the host has no git repo to unpack them from.
ssh "$HOST" "(if exist \"$DEST\\releases\" rmdir /s /q \"$DEST\\releases\") & echo ok" >/dev/null
for ref in $(grep -rhoE '^launch +v[0-9][0-9.]*' "$REPO/scenarios" | awk '{print $2}' | sort -u) ${REFS:-}; do
  echo "==> staging $ref"
  ui="$(git -C "$REPO" rev-parse "$ref:vendor/chotic-ui")"
  ssh "$HOST" "mkdir \"$DEST\\releases\\$ref\\vendor\\chotic-ui\"" >/dev/null
  git -C "$REPO" archive "$ref" | ssh "$HOST" "tar xf - -C \"$FWD/releases/$ref\""
  git -C "$REPO/vendor/chotic-ui" archive "$ui" | ssh "$HOST" "tar xf - -C \"$FWD/releases/$ref/vendor/chotic-ui\""
done
scp -q "$AUTH/token.json" "$AUTH/credentials.json" "$HOST:$FWD/auth/"

PS="powershell -NoProfile -ExecutionPolicy Bypass -File"
ssh "$HOST" "$PS \"$DEST\\src\\scripts\\windows_prepare.ps1\" -Base \"$DEST\" $([ "$APP" = 1 ] && echo -Build)"

APPARG=""
[ "$APP" = 1 ] && APPARG="--app \"$DEST\\src\\dist\\synchotic-app\\synchotic-app.exe\""

echo "==> scenarios on $HOST"
set +e
ssh "$HOST" "cd /d \"$DEST\\src\" && set GOOGLE_API_KEY=$KEY&& set PYTHONIOENCODING=utf-8&& ..\\venv\\Scripts\\python -u scripts\\scenarios.py --auth \"$DEST\\auth\" $APPARG $*"
status=$?
set -e

mkdir -p "$REPO/runs/windows"
ssh "$HOST" "cd /d \"$DEST\\src\" && tar czf - runs" 2>/dev/null | tar xzf - -C "$REPO/runs/windows" 2>/dev/null || true
exit $status
