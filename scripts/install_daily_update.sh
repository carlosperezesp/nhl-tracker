#!/usr/bin/env bash
# Installs two LaunchAgents:
#   1. update-data  — 06:00 daily: updates all sport data files (NHL/NBA/MLB/NFL)
#   2. newsletter   — 07:05 daily: sends the newsletter email (requires .env GMAIL_APP_PASSWORD)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="$(command -v python3)"
AGENTS_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$AGENTS_DIR"

# ── 1. Daily data update (no email dependency) ─────────────────────
DATA_PLIST="$AGENTS_DIR/com.local.nhl-tracker.update-data.plist"
cat > "$DATA_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.local.nhl-tracker.update-data</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON_BIN</string>
    <string>$ROOT/scripts/update_all_data.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>6</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$ROOT/nhl-tracker-update.log</string>
  <key>StandardErrorPath</key>
  <string>$ROOT/nhl-tracker-update.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key>
    <string>$HOME</string>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin</string>
  </dict>
</dict>
</plist>
PLIST

# ── 2. Daily newsletter email ──────────────────────────────────────
NEWS_PLIST="$AGENTS_DIR/com.local.nhl-tracker.update.plist"
cat > "$NEWS_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.local.nhl-tracker.update</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON_BIN</string>
    <string>$ROOT/scripts/send_newsletter.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>7</integer>
    <key>Minute</key>
    <integer>5</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$ROOT/nhl-tracker-update.log</string>
  <key>StandardErrorPath</key>
  <string>$ROOT/nhl-tracker-update.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key>
    <string>$HOME</string>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin</string>
  </dict>
</dict>
</plist>
PLIST

# ── Load both agents ───────────────────────────────────────────────
for PLIST in "$DATA_PLIST" "$NEWS_PLIST"; do
  launchctl unload "$PLIST" >/dev/null 2>&1 || true
  launchctl load "$PLIST"
done

echo "Instalado:"
echo "  - Actualización de datos:   06:00 diario (NHL + NBA + MLB + NFL)"
echo "  - Newsletter email:         07:05 diario (requiere GMAIL_APP_PASSWORD en .env)"
echo "  Log: $ROOT/nhl-tracker-update.log"
