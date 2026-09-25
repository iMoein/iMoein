#!/bin/bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/Scripts"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs"
LABEL="com.imoein.github-profile-telemetry"
PLIST="$LAUNCH_DIR/$LABEL.plist"
OLD_LABEL="com.imoein.github-editor-sync"
OLD_PLIST="$LAUNCH_DIR/$OLD_LABEL.plist"
UID_NOW="$(id -u)"

mkdir -p "$BIN_DIR" "$LAUNCH_DIR" "$LOG_DIR"

install -m 700 \
  "$SOURCE_DIR/collect_github_yesterday.py" \
  "$BIN_DIR/collect-github-yesterday.py"

install -m 700 \
  "$SOURCE_DIR/update_history.py" \
  "$BIN_DIR/update-history.py"

install -m 700 \
  "$SOURCE_DIR/backfill_history.py" \
  "$BIN_DIR/backfill-history.py"

install -m 700 \
  "$SOURCE_DIR/publish_daily_telemetry.sh" \
  "$BIN_DIR/publish-github-profile-telemetry.sh"

launchctl bootout "gui/$UID_NOW/$OLD_LABEL" >/dev/null 2>&1 || true
rm -f "$OLD_PLIST"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$BIN_DIR/publish-github-profile-telemetry.sh</string>
  </array>

  <key>RunAtLoad</key>
  <true/>

  <key>StartInterval</key>
  <integer>3600</integer>

  <key>StandardOutPath</key>
  <string>$LOG_DIR/imoein-profile-telemetry.log</string>

  <key>StandardErrorPath</key>
  <string>$LOG_DIR/imoein-profile-telemetry-error.log</string>
</dict>
</plist>
EOF

plutil -lint "$PLIST" >/dev/null

launchctl bootout "gui/$UID_NOW/$LABEL" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UID_NOW" "$PLIST"
launchctl kickstart "gui/$UID_NOW/$LABEL"

echo "Installed $LABEL"
echo "LaunchAgent: $PLIST"
echo "Publisher: $BIN_DIR/publish-github-profile-telemetry.sh"
echo "Collector: $BIN_DIR/collect-github-yesterday.py"
echo "History updater: $BIN_DIR/update-history.py"
echo "History backfill: $BIN_DIR/backfill-history.py"
