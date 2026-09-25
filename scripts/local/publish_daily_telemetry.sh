#!/bin/bash
set -euo pipefail

REPO_URL="${PROFILE_REPO_URL:-https://github.com/iMoein/iMoein.git}"
BRANCH="${PROFILE_BRANCH:-main}"
GIT_NAME="${PROFILE_GIT_NAME:-Moein}"
GIT_EMAIL="${PROFILE_GIT_EMAIL:-13425551+iMoein@users.noreply.github.com}"
GITHUB_USERNAME="${PROFILE_GITHUB_USERNAME:-iMoein}"
PROFILE_REPOSITORY="${PROFILE_REPOSITORY:-iMoein/iMoein}"

WORKROOT="$HOME/.local/share/imoein-profile-sync"
WORKDIR="$WORKROOT/repo"
STATE_DIR="$HOME/.local/state/imoein-profile-sync"
STATE_FILE="$STATE_DIR/last-processed-date"
LEGACY_STATE_FILE="$STATE_DIR/last-success-date"
COLLECTOR="$HOME/Scripts/collect-github-yesterday.py"
HISTORY_UPDATER="$HOME/Scripts/update-history.py"

TODAY="$(date +%Y-%m-%d)"
YESTERDAY="$(/usr/bin/python3 - <<'PY'
import datetime as dt
print((dt.datetime.now().astimezone().date() - dt.timedelta(days=1)).isoformat())
PY
)"

mkdir -p "$WORKROOT" "$STATE_DIR"

# Offline runs do not advance state.
if ! /usr/bin/curl --silent --fail --max-time 10 https://github.com/ >/dev/null 2>&1; then
  exit 0
fi

if [[ ! -f "$COLLECTOR" ]]; then
  echo "Telemetry collector not found: $COLLECTOR" >&2
  exit 1
fi

if [[ ! -f "$HISTORY_UPDATER" ]]; then
  echo "History updater not found: $HISTORY_UPDATER" >&2
  exit 1
fi
VSCODE_APP="/Applications/Visual Studio Code.app"
if [[ ! -d "$VSCODE_APP" && -d "$HOME/Applications/Visual Studio Code.app" ]]; then
  VSCODE_APP="$HOME/Applications/Visual Studio Code.app"
fi

if [[ ! -d "$VSCODE_APP" ]]; then
  echo "Visual Studio Code not found." >&2
  exit 1
fi

VSCODE_VERSION="$(
  /usr/libexec/PlistBuddy     -c 'Print :CFBundleShortVersionString'     "$VSCODE_APP/Contents/Info.plist"
)"

if [[ -z "$VSCODE_VERSION" ]]; then
  echo "Unable to detect VS Code version." >&2
  exit 1
fi

if [[ ! -d "$WORKDIR/.git" ]]; then
  rm -rf "$WORKDIR"
  /usr/bin/git clone "$REPO_URL" "$WORKDIR"
fi

cd "$WORKDIR"
/usr/bin/git remote set-url origin "$REPO_URL"
/usr/bin/git fetch origin "$BRANCH"
/usr/bin/git checkout -B "$BRANCH" "origin/$BRANCH"
/usr/bin/git config user.name "$GIT_NAME"
/usr/bin/git config user.email "$GIT_EMAIL"

export VSCODE_VERSION
export PROFILE_GITHUB_USERNAME="$GITHUB_USERNAME"
export PROFILE_REPOSITORY

ACTIVITY_FILE="$WORKDIR/stats/yesterday.json"
HISTORY_FILE="$WORKDIR/stats/history.json"
# Migrate state from the committed snapshot. The old execution-date state is
# intentionally ignored because it cannot tell us which activity day was processed.
LAST_PROCESSED="$(
  /usr/bin/python3 - "$STATE_FILE" "$ACTIVITY_FILE" "$YESTERDAY" <<'PY'
import datetime as dt
import json
import pathlib
import sys

state_path = pathlib.Path(sys.argv[1])
snapshot_path = pathlib.Path(sys.argv[2])
yesterday = dt.date.fromisoformat(sys.argv[3])
candidates = []

if state_path.exists():
    try:
        candidates.append(dt.date.fromisoformat(state_path.read_text().strip()))
    except ValueError:
        pass

if snapshot_path.exists():
    try:
        value = json.loads(snapshot_path.read_text()).get("date")
        if value:
            candidates.append(dt.date.fromisoformat(value))
    except (OSError, ValueError, json.JSONDecodeError):
        pass

if candidates:
    last = max(candidates)
    print(min(last, yesterday).isoformat())
else:
    print((yesterday - dt.timedelta(days=1)).isoformat())
PY
)"

PENDING_DATES="$(
  /usr/bin/python3 - "$LAST_PROCESSED" "$YESTERDAY" <<'PY'
import datetime as dt
import sys

cursor = dt.date.fromisoformat(sys.argv[1]) + dt.timedelta(days=1)
end = dt.date.fromisoformat(sys.argv[2])
while cursor <= end:
    print(cursor.isoformat())
    cursor += dt.timedelta(days=1)
PY
)"
# Update the editor version once. If backlog exists, this change rides with the
# first telemetry commit; otherwise it can be committed independently.
EDITOR_CHANGED=0
/usr/bin/python3 <<'PY'
import os
import re
from pathlib import Path

path = Path("profile.json")
text = path.read_text(encoding="utf-8")
version = os.environ["VSCODE_VERSION"]
pattern = r'("ide"\s*:\s*"VS Code )\d+(?:\.\d+)*'
updated, count = re.subn(pattern, lambda match: match.group(1) + version, text, count=1)
if count != 1:
    raise SystemExit("VS Code ide field not found in profile.json")
path.write_text(updated, encoding="utf-8")
PY

if ! /usr/bin/git diff --quiet -- profile.json; then
  EDITOR_CHANGED=1
fi

COMMIT_COUNT=0
if [[ -n "$PENDING_DATES" ]]; then
  while IFS= read -r ACTIVITY_DATE; do
    [[ -z "$ACTIVITY_DATE" ]] && continue

    /usr/bin/python3 "$COLLECTOR" "$ACTIVITY_FILE" "$ACTIVITY_DATE"
    /usr/bin/python3 "$HISTORY_UPDATER" "$ACTIVITY_FILE" "$HISTORY_FILE" 400
    /usr/bin/git add stats/yesterday.json stats/history.json profile.json

    if /usr/bin/git diff --cached --quiet; then
      continue
    fi

    if [[ "$ACTIVITY_DATE" == "$YESTERDAY" ]]; then
      MESSAGE="chore: update daily telemetry for $ACTIVITY_DATE"
    else
      MESSAGE="chore: backfill daily telemetry for $ACTIVITY_DATE"
    fi

    /usr/bin/git commit -m "$MESSAGE"
    COMMIT_COUNT=$((COMMIT_COUNT + 1))
  done <<< "$PENDING_DATES"
elif [[ "$EDITOR_CHANGED" -eq 1 ]]; then
  /usr/bin/git add profile.json
  /usr/bin/git commit -m "chore: update VS Code to $VSCODE_VERSION"
  COMMIT_COUNT=1
fi
if [[ "$COMMIT_COUNT" -gt 0 ]]; then
  # Rebase immediately before publishing in case GitHub Actions updated the
  # generated SVG while this run was collecting historical telemetry.
  /usr/bin/git pull --rebase origin "$BRANCH"
  /usr/bin/git push origin "$BRANCH"
fi

# Advance state only after all required commits have been pushed successfully.
printf '%s\n' "$YESTERDAY" > "$STATE_FILE"
rm -f "$LEGACY_STATE_FILE"

if [[ "$COMMIT_COUNT" -gt 0 ]]; then
  echo "Telemetry sync complete: commits=$COMMIT_COUNT through=$YESTERDAY vscode=$VSCODE_VERSION"
else
  echo "Telemetry already current through $YESTERDAY; no commit required."
fi
