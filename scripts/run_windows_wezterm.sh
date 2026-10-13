#!/usr/bin/env bash
# Run scripts/windows_wezterm_check.py on a Windows host: drag-resize and paste
# in a real WezTerm window.
#
#   scripts/run_windows_wezterm.sh winprox
#   scripts/run_windows_wezterm.sh winprox path/to/other.lua    check another config
#
# The check needs the host's interactive desktop, so it runs as a scheduled
# task in the logged-in user's session, and that session has to be logged in.
# It opens and closes WezTerm windows there. Reads the WezTerm the launcher
# downloaded; run the launcher once on the host if there is none.
set -euo pipefail

HOST="${1:?usage: run_windows_wezterm.sh <ssh-host> [wezterm.lua]}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LUA="${2:-$REPO/packaging/macos/wezterm.lua}"

PROFILE="$(ssh "$HOST" 'echo %USERPROFILE%' | tr -d '\r')"
DEST="$PROFILE\\synchotic-validate"
FWD="${DEST//\\//}"

ssh "$HOST" "(if exist \"$DEST\\wezterm-check\" rmdir /s /q \"$DEST\\wezterm-check\") & mkdir \"$DEST\\wezterm-check\\src\\scripts\" \"$DEST\\wezterm-check\\src\\vendor\" & echo ok" >/dev/null
scp -q "$REPO/scripts/windows_wezterm_check.py" "$HOST:$FWD/wezterm-check/src/scripts/"
scp -q "$LUA" "$HOST:$FWD/wezterm-check/wezterm.lua"
COPYFILE_DISABLE=1 tar czf - -C "$REPO/vendor" --exclude __pycache__ --exclude tests chotic-ui \
  | ssh "$HOST" "tar xzf - -C \"$FWD/wezterm-check/src/vendor\""
ssh "$HOST" "\"$DEST\\venv\\Scripts\\python\" -m pip install -q psutil" >/dev/null

TASK=synchotic-wezterm-check
# schtasks takes 261 characters of command at most, so the command is a file.
RUN="$(mktemp)"
printf '@"%s\\venv\\Scripts\\python.exe" "%s\\wezterm-check\\src\\scripts\\windows_wezterm_check.py" --lua "%s\\wezterm-check\\wezterm.lua" --out "%s\\wezterm-check\\out" > "%s\\wezterm-check\\run.log" 2>&1\r\n' \
  "$DEST" "$DEST" "$DEST" "$DEST" "$DEST" > "$RUN"
scp -q "$RUN" "$HOST:$FWD/wezterm-check/run.cmd"
rm -f "$RUN"
ssh "$HOST" "schtasks /create /tn $TASK /tr \"$DEST\\wezterm-check\\run.cmd\" /sc once /st 23:59 /it /f >nul & schtasks /run /tn $TASK >nul"
echo "==> running in $HOST's desktop session"
for _ in $(seq 1 120); do
  sleep 3
  if ssh "$HOST" "if exist \"$DEST\\wezterm-check\\out\\result.json\" (echo done)" | grep -q done; then break; fi
done
ssh "$HOST" "schtasks /delete /tn $TASK /f >nul" || true
RESULT="$(ssh "$HOST" "type \"$DEST\\wezterm-check\\out\\result.json\"" | tr -d '\r')"
echo "$RESULT"
echo "$RESULT" | python3 -c '
import json, sys
r = json.load(sys.stdin)
bad = {k: v["problems"] for k, v in r.items() if v["problems"]}
for k in r:
    print(("FAIL " if k in bad else "PASS ") + k + "".join("\n    " + p for p in bad.get(k, [])))
sys.exit(1 if bad else 0)'
