#!/bin/bash
# Installation script for Telegram CLI Bridge

set -e

echo "🚀 Installing Telegram CLI Bridge..."

# Get the project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed. Please install it first:"
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Install dependencies
echo "📦 Installing dependencies..."
cd "$PROJECT_DIR"
uv sync

# Check if .env exists
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "⚠️  No .env file found. Creating from .env.example..."
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    echo ""
    echo "📝 Please edit $PROJECT_DIR/.env with your configuration:"
    echo "   - TELEGRAM_BOT_TOKEN (get from @BotFather)"
    echo "   - ALLOWED_USER_ID (get from @userinfobot)"
    echo "   - CLI_COMMAND (default: claude)"
    echo ""
fi

# Create symlink in user's local bin
LOCAL_BIN="$HOME/.local/bin"
mkdir -p "$LOCAL_BIN"

# Remove old symlink if exists
if [ -L "$LOCAL_BIN/tg-bridge" ]; then
    rm "$LOCAL_BIN/tg-bridge"
fi

# Create new symlink
ln -s "$PROJECT_DIR/tg-bridge" "$LOCAL_BIN/tg-bridge"

echo "✅ Installation complete!"
echo ""
echo "📍 Script installed to: $LOCAL_BIN/tg-bridge"
echo ""

# Check if ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$LOCAL_BIN:"* ]]; then
    echo "⚠️  $LOCAL_BIN is not in your PATH."
    echo ""
    echo "Add this to your shell profile (~/.bashrc, ~/.zshrc, etc.):"
    echo ""
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
    echo "Then reload your shell: source ~/.bashrc (or ~/.zshrc)"
else
    echo "✅ $LOCAL_BIN is already in your PATH"
fi

echo ""
echo "🎯 Usage:"
echo "   tg-bridge              # Start the bot (from anywhere)"
echo "   tg-bridge --help       # Show help"
echo ""
echo "📝 Next steps:"
echo "   1. Edit $PROJECT_DIR/.env with your configuration"
echo "   2. Run: tg-bridge"
echo ""
