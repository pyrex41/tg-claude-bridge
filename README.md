# Telegram Claude Bridge

Autonomous Telegram bot for task-master integration with AI agents (OpenCode/Grok, LangChain/Groq).

> **Quick Start:** Install with `uv pip install -e .` and run `tg-bridge` from anywhere!

## Three Bot Variants

This project provides three different bot implementations:

1. **`tg-bridge`** (main_opencode.py) - Recommended autonomous bot with OpenCode/Grok
2. **`tg-bridge-langchain`** (main_langchain.py) - LangChain/Groq dual-agent system
3. **`tg-bridge-legacy`** (main.py) - Original subprocess-based CLI bridge

## Features (`tg-bridge` - OpenCode Bot)

- 🤖 **Autonomous Task Execution** - Automatically works through task-master tasks
- 🧠 **AI-Powered Decisions** - Smart completion verification and error handling
- 🔄 **Model Switching** - Switch between Grok models on the fly (`/models`)
- 📋 **Clean Task Display** - Parsed, chat-friendly task lists (`/tasks`)
- 🔧 **Real-Time Updates** - See tool calls, file edits, and progress live
- 📁 **Multi-Directory** - Work on multiple projects (`/project`)
- 💰 **Cost Tracking** - Monitor API usage per step
- 🔒 **Single-User Security** - Telegram user ID authentication

## Requirements

- Python 3.13+
- Telegram account
- `uv` package manager ([installation guide](https://github.com/astral-sh/uv))

## Installation

```bash
# Clone and navigate
cd /path/to/tg-claude-bridge

# Install globally with uv
uv pip install -e .

# This creates three CLI commands:
# - tg-bridge (OpenCode bot - recommended)
# - tg-bridge-langchain (LangChain bot)
# - tg-bridge-legacy (subprocess bot)
```

## Configuration

Create `.env` in your project directory:

```bash
# Required
TELEGRAM_BOT_TOKEN="your_bot_token"        # From @BotFather
ALLOWED_USER_ID="your_user_id"             # From @userinfobot

# OpenCode Configuration
OPENCODE_MODEL="xai/grok-4-fast-non-reasoning"
WORKING_DIRECTORY="/path/to/your/project"
AUTO_CONTINUE=true
REQUIRE_APPROVAL=false

# API Keys
XAI_API_KEY="your_xai_key"                 # Required for Grok models
GROQ_API_KEY="your_groq_key"               # Optional, for LangChain bot
ANTHROPIC_API_KEY="your_anthropic_key"     # Optional
```

Get your credentials:
- **Bot Token**: Message [@BotFather](https://t.me/botfather) on Telegram, send `/newbot`
- **User ID**: Message [@userinfobot](https://t.me/userinfobot), send `/start`
- **XAI Key**: Get from [x.ai](https://x.ai)

## Usage

### Start the bot

From anywhere on your computer:
```bash
tg-bridge
```

From a specific project:
```bash
cd /path/to/your/project
tg-bridge
```

The bot loads `.env` from the current directory, or uses the one in the install directory.

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

### Telegram Commands

- `/start` - Show help and current configuration
- `/auto` - Start autonomous task-master workflow
- `/next` - Work on next task manually
- `/tasks` - List all pending tasks (clean, parsed format)
- `/models` - Switch AI models interactively
  - 1 = Grok Code Fast 1 (coding optimized)
  - 2 = Grok 4 Fast Non-Reasoning (faster)
  - 3 = Grok 4 Fast Reasoning (advanced)
- `/status` - Show current bot status and active task
- `/pause` / `/resume` - Control autonomous mode
- `/complete` - Mark current task as complete
- `/retry` - Retry current task with fresh context
- `/project <path>` - Change working directory
- `/clear` - Clear agent session and start fresh

### Example Workflow

1. Start the bot: `tg-bridge`
2. In Telegram, send `/start` to see configuration
3. Send `/tasks` to see what needs to be done
4. Send `/auto` to start autonomous execution
5. Watch as the bot:
   - Gets the next task from task-master
   - Uses AI to work on it
   - Shows real-time updates (tool calls, file edits)
   - Verifies completion with AI
   - Automatically moves to the next task
6. Use `/pause` if you need to interrupt
7. Use `/models 1` to switch models if needed

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
