# Telegram CLI Bridge Bot

A lightweight Python bot that enables remote interaction with command-line interface (CLI) tools from Telegram. Perfect for managing interactive CLI sessions from your mobile device.

> **Quick Start:** New here? Check out [QUICKSTART.md](QUICKSTART.md) for a 5-minute setup guide!

## Documentation

- 📖 **[QUICKSTART.md](QUICKSTART.md)** - Get started in 5 minutes
- 📋 **[INSTALL_SUMMARY.md](INSTALL_SUMMARY.md)** - Post-installation guide
- 📚 **README.md** - Complete documentation (you are here)

## Features

- 🔄 Bidirectional communication between Telegram and CLI processes
- 🔒 Single-user security with Telegram user ID authentication
- 📱 Remote CLI access from any Telegram-enabled device
- ⚡ Real-time input/output relay with low latency
- 🧩 Configurable prompt detection for various CLI tools
- 📦 Built with `uv` for fast, modern Python package management

## Requirements

- Python 3.13+
- Telegram account
- `uv` package manager ([installation guide](https://github.com/astral-sh/uv))

## Installation

### Quick Install (Recommended)

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd tg-claude-bridge
   ```

2. **Run the installer:**
   ```bash
   ./install.sh
   ```

   This will:
   - Install dependencies via `uv`
   - Create a `.env` file from template
   - Install `tg-bridge` command to `~/.local/bin`

3. **Create a Telegram Bot:**
   - Open Telegram and search for [@BotFather](https://t.me/botfather)
   - Send `/newbot` and follow the instructions
   - Save the bot token provided

4. **Get your Telegram User ID:**
   - Search for [@userinfobot](https://t.me/userinfobot) on Telegram
   - Send `/start` to get your user ID

5. **Configure environment variables:**
   Edit `~/.../tg-claude-bridge/.env` with your settings:
   ```env
   TELEGRAM_BOT_TOKEN="your_bot_token_here"
   ALLOWED_USER_ID="your_telegram_user_id_here"
   CLI_COMMAND="claude"  # or any other CLI command
   ```

6. **Ensure `~/.local/bin` is in your PATH:**

   Add to your `~/.zshrc` or `~/.bashrc`:
   ```bash
   export PATH="$HOME/.local/bin:$PATH"
   ```

   Then reload: `source ~/.zshrc`

### Manual Installation

If you prefer manual setup:

```bash
git clone <repository-url>
cd tg-claude-bridge
uv sync
cp .env.example .env
# Edit .env with your configuration
```

## Usage

### Start the bot (from anywhere):

```bash
tg-bridge
```

Or if you didn't install system-wide:

```bash
cd /path/to/tg-claude-bridge
uv run python main.py
```

### Run as background service (optional):

#### macOS (LaunchAgent):

```bash
# Copy the plist file to LaunchAgents
cp com.user.tg-cli-bridge.plist ~/Library/LaunchAgents/

# Load the service
launchctl load ~/Library/LaunchAgents/com.user.tg-cli-bridge.plist

# Start the service
launchctl start com.user.tg-cli-bridge
```

**Manage the service:**
```bash
# Stop
launchctl stop com.user.tg-cli-bridge

# Unload (disable auto-start)
launchctl unload ~/Library/LaunchAgents/com.user.tg-cli-bridge.plist

# View logs
tail -f ~/path/to/tg-claude-bridge/logs/tg-bridge.log
```

#### Linux (systemd):

```bash
# Copy service file
sudo cp tg-cli-bridge.service /etc/systemd/user/

# Reload systemd
systemctl --user daemon-reload

# Enable and start
systemctl --user enable tg-cli-bridge.service
systemctl --user start tg-cli-bridge.service

# Check status
systemctl --user status tg-cli-bridge.service
```

### Telegram Commands:

- `/start` - Launch the CLI process
- `/stop` - Terminate the CLI process
- Any text message - Send input to the running CLI

### Example Workflow:

1. Send `/start` to your bot on Telegram
2. Bot launches the CLI (e.g., "claude") and relays its output
3. Respond to prompts by sending text messages
4. Bot forwards your input to the CLI and sends back responses
5. Send `/stop` when done to terminate the session

## Configuration

All configuration is managed through environment variables in `.env`:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | - | Bot token from @BotFather |
| `ALLOWED_USER_ID` | ✅ | - | Your Telegram user ID (numeric) |
| `CLI_COMMAND` | ✅ | `claude` | Command to launch the CLI |
| `PROMPT_REGEX` | ❌ | `.*[>?]$` | Regex pattern to detect CLI prompts |
| `CLI_TIMEOUT` | ❌ | `30` | Timeout in seconds for CLI operations |

### Custom Prompt Detection

Different CLIs may use different prompt formats. Customize the `PROMPT_REGEX` to match your CLI's output pattern:

```env
# For prompts ending with ">" or "?"
PROMPT_REGEX=".*[>?]$"

# For prompts ending with ":"
PROMPT_REGEX=".*:$"

# For Python interactive shell
PROMPT_REGEX=">>>"
```

## Security

- **User Authentication**: Only the specified `ALLOWED_USER_ID` can interact with the bot
- **Environment Variables**: Sensitive data stored securely in `.env` (not committed to git)
- **Local Deployment**: Bot runs on your local machine, not exposed to external servers

## Platform Compatibility

- ✅ **Linux/macOS**: Full support via `pexpect`
- ⚠️ **Windows**: Limited support (requires WSL or `pexpect-windows`)

## Project Structure

```
tg-claude-bridge/
├── main.py              # Main bot implementation
├── pyproject.toml       # uv project configuration
├── .env.example         # Environment variables template
├── .env                 # Your configuration (gitignored)
├── .taskmaster/         # Task Master AI project management
└── README.md            # This file
```

## Development

This project uses [Task Master AI](https://github.com/cyanheads/task-master-ai) for task management. To view tasks:

```bash
task-master list
```

## Troubleshooting

### Bot doesn't respond
- Verify `TELEGRAM_BOT_TOKEN` is correct
- Check `ALLOWED_USER_ID` matches your Telegram user ID
- Ensure bot is running (`uv run python main.py`)

### CLI doesn't start
- Verify `CLI_COMMAND` is installed and in PATH
- Check CLI launches successfully from terminal: `<your-cli-command>`

### Output not captured
- Adjust `PROMPT_REGEX` to match your CLI's prompt format
- Increase `CLI_TIMEOUT` for slower CLIs

### Unauthorized message
- Confirm you're messaging from the correct Telegram account
- Verify `ALLOWED_USER_ID` in `.env` matches your user ID

## License

MIT License - see LICENSE file for details

## Contributing

Contributions welcome! Please open an issue or submit a pull request.

## Acknowledgments

Built with:
- [python-telegram-bot](https://python-telegram-bot.org/) - Telegram Bot API wrapper
- [pexpect](https://pexpect.readthedocs.io/) - Process automation
- [uv](https://github.com/astral-sh/uv) - Fast Python package manager
