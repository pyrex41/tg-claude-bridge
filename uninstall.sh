#!/bin/bash
# Uninstallation script for Telegram CLI Bridge

set -e

echo "🗑️  Uninstalling Telegram CLI Bridge..."

LOCAL_BIN="$HOME/.local/bin"

# Remove symlink
if [ -L "$LOCAL_BIN/tg-bridge" ]; then
    rm "$LOCAL_BIN/tg-bridge"
    echo "✅ Removed command: $LOCAL_BIN/tg-bridge"
else
    echo "ℹ️  Command not found: $LOCAL_BIN/tg-bridge"
fi

# Remove LaunchAgent if exists (macOS)
if [ -f "$HOME/Library/LaunchAgents/com.user.tg-cli-bridge.plist" ]; then
    echo "🔍 Found LaunchAgent, removing..."
    launchctl unload "$HOME/Library/LaunchAgents/com.user.tg-cli-bridge.plist" 2>/dev/null || true
    rm "$HOME/Library/LaunchAgents/com.user.tg-cli-bridge.plist"
    echo "✅ Removed LaunchAgent"
fi

# Remove systemd service if exists (Linux)
if [ -f "/etc/systemd/user/tg-cli-bridge.service" ]; then
    echo "🔍 Found systemd service, removing..."
    systemctl --user stop tg-cli-bridge.service 2>/dev/null || true
    systemctl --user disable tg-cli-bridge.service 2>/dev/null || true
    sudo rm /etc/systemd/user/tg-cli-bridge.service
    systemctl --user daemon-reload
    echo "✅ Removed systemd service"
fi

echo ""
echo "✅ Uninstallation complete!"
echo ""
echo "Note: Project directory still exists. To completely remove:"
echo "  rm -rf $(pwd)"
echo ""
