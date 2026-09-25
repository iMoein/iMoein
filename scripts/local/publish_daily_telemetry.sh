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
STATE_FILE="$STATE_DIR/last-success-date"
COLLECTOR="$HOME/Scripts/collect-github-yesterday.py"
TODAY="$(date +%Y-%m-%d)"

mkdir -p "$WORKROOT" "$STATE_DIR"

if [[ -f "$STATE_FILE" ]] && [[ "$(cat "$STATE_FILE")" == "$TODAY" ]]; then
  exit 0
fi

if ! /usr/bin/curl --silent --fail --max-time 10 https://github.com/ >/dev/null 2>&1; then
  exit 0
fi

if [[ ! -f "$COLLECTOR" ]]; then
  echo "Telemetry collector not found: $COLLECTOR" >&2
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
/usr/bin/python3 "$COLLECTOR" "$ACTIVITY_FILE"
ACTIVITY_DATE="$(
  /usr/bin/python3 -c     'import json; print(json.load(open("stats/yesterday.json"))["date"])'
)"

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

/usr/bin/git add profile.json stats/yesterday.json

if /usr/bin/git diff --cached --quiet; then
  printf '%s\n' "$TODAY" > "$STATE_FILE"
  echo "Daily telemetry already current for $ACTIVITY_DATE."
  exit 0
fi
/usr/bin/git commit -m "chore: update daily telemetry for ${ACTIVITY_DATE}"

/usr/bin/git pull --rebase origin "$BRANCH"
/usr/bin/git push origin "$BRANCH"

printf '%s\n' "$TODAY" > "$STATE_FILE"
echo "Daily profile telemetry published: date=${ACTIVITY_DATE} vscode=${VSCODE_VERSION}"
