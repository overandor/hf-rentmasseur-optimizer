#!/bin/zsh
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${RM_VISITOR_PYTHON:-$(command -v python3)}"
ENV_FILE="${RM_VISITOR_ENV_FILE:-$HOME/.config/rm-visitor-telemetry.env}"
LOG_DIR="$HOME/Library/Logs/RMVisitorTelemetry"
AGENT_DIR="$HOME/Library/LaunchAgents"
SCAN_LABEL="com.overandor.rm-visitor-telemetry"
DASH_LABEL="com.overandor.rm-visitor-dashboard"
SCAN_PLIST="$AGENT_DIR/$SCAN_LABEL.plist"
DASH_PLIST="$AGENT_DIR/$DASH_LABEL.plist"
[[ -f "$ENV_FILE" ]] || { echo "Missing $ENV_FILE"; exit 1; }
[[ "$(stat -f '%Lp' "$ENV_FILE")" == "600" ]] || { echo "Run: chmod 600 '$ENV_FILE'"; exit 1; }
mkdir -p "$LOG_DIR" "$AGENT_DIR" "$REPO_ROOT/data" "$REPO_ROOT/output"
SCAN_COMMAND="set -a; source '$ENV_FILE'; set +a; cd '$REPO_ROOT'; '$PYTHON_BIN' -m rm_traffic.visitor_telemetry scan --cooldown-hours 24 --area new-york"
DASH_COMMAND="cd '$REPO_ROOT'; '$PYTHON_BIN' -m rm_traffic.visitor_telemetry serve --host 127.0.0.1 --port 8787 --area new-york"
cat > "$SCAN_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict><key>Label</key><string>$SCAN_LABEL</string><key>ProgramArguments</key><array><string>/bin/zsh</string><string>-lc</string><string>$SCAN_COMMAND</string></array><key>StartInterval</key><integer>900</integer><key>RunAtLoad</key><true/><key>StandardOutPath</key><string>$LOG_DIR/collector.log</string><key>StandardErrorPath</key><string>$LOG_DIR/collector-error.log</string><key>ProcessType</key><string>Background</string></dict></plist>
PLIST
cat > "$DASH_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict><key>Label</key><string>$DASH_LABEL</string><key>ProgramArguments</key><array><string>/bin/zsh</string><string>-lc</string><string>$DASH_COMMAND</string></array><key>RunAtLoad</key><true/><key>KeepAlive</key><true/><key>StandardOutPath</key><string>$LOG_DIR/dashboard.log</string><key>StandardErrorPath</key><string>$LOG_DIR/dashboard-error.log</string><key>ProcessType</key><string>Background</string></dict></plist>
PLIST
launchctl bootout "gui/$UID/$SCAN_LABEL" 2>/dev/null || true
launchctl bootout "gui/$UID/$DASH_LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$SCAN_PLIST"
launchctl bootstrap "gui/$UID" "$DASH_PLIST"
launchctl kickstart -k "gui/$UID/$SCAN_LABEL"
launchctl kickstart -k "gui/$UID/$DASH_LABEL"
echo "Collector: every 15 minutes"
echo "Dashboard: http://127.0.0.1:8787"
echo "Database: $REPO_ROOT/data/rm_visitor_telemetry.sqlite3"
echo "Logs: $LOG_DIR"
