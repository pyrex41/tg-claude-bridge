# Telegram Claude Bridge

Autonomous Telegram bot for task-master integration with AI agents (OpenCode/Grok, LangChain/Groq).

> **Quick Start:**
> ```bash
> git clone https://github.com/yourusername/tg-claude-bridge.git
> cd tg-claude-bridge
> uv pip install -e . && pnpm install
> cp .env.example .env  # Then configure your credentials
> tg-bridge
> ```

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

### System Requirements
- **Python 3.13+** (Check with `python --version`)
- **Node.js 18+** (Check with `node --version`)
- **Telegram account**

### Package Managers
- **`uv`** - Fast Python package manager ([installation guide](https://github.com/astral-sh/uv))
  ```bash
  # Install uv (macOS/Linux)
  curl -LsSf https://astral.sh/uv/install.sh | sh

  # Install uv (Windows)
  powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

- **`pnpm`** - Fast, disk space efficient Node.js package manager ([installation guide](https://pnpm.io/installation))
  ```bash
  # Install pnpm (macOS/Linux)
  curl -fsSL https://get.pnpm.io/install.sh | sh -

  # Install pnpm (Windows)
  powershell -c "irm https://get.pnpm.io/install.ps1 | iex"

  # Or via npm (if you have it)
  npm install -g pnpm

  # Or via Homebrew (macOS)
  brew install pnpm
  ```

## Installation

Follow these steps to install the Telegram Claude Bridge on your system:

### 1. Clone the Repository

```bash
# Clone the repository
git clone https://github.com/yourusername/tg-claude-bridge.git

# Navigate into the project directory
cd tg-claude-bridge
```

### 2. Install Python Dependencies

```bash
# Install the package in editable mode with uv
uv pip install -e .

# This creates three CLI commands available globally:
# - tg-bridge (OpenCode bot - recommended)
# - tg-bridge-langchain (LangChain bot)
# - tg-bridge-legacy (subprocess bot)
```

**Note:** The `-e` flag installs in "editable" mode, meaning changes to the source code are immediately reflected without reinstalling.

### 3. Install Node.js Dependencies

```bash
# Install Node.js packages with pnpm (required for Claude Code SDK)
pnpm install
```

### 4. Verify Installation

```bash
# Check that the CLI commands are available
which tg-bridge
which tg-bridge-langchain
which tg-bridge-legacy

# All three commands should show paths in your Python environment
```

### 5. Configure Environment Variables

Create a `.env` file in the project directory (copy from `.env.example`):

```bash
# Copy the example configuration
cp .env.example .env

# Edit with your credentials
nano .env  # or use your preferred editor
```

Required configuration (see Configuration section below for details):
- `TELEGRAM_BOT_TOKEN` - From @BotFather on Telegram
- `ALLOWED_USER_ID` - Your Telegram user ID
- `XAI_API_KEY` - For Grok models
- `WORKING_DIRECTORY` - Path to your project

### Installation Complete!

You can now run the bot from anywhere:
```bash
tg-bridge
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

### Installation Issues

#### `uv` command not found
```bash
# Install uv first
curl -LsSf https://astral.sh/uv/install.sh | sh

# Add to PATH (may be needed)
export PATH="$HOME/.cargo/bin:$PATH"
```

#### `pnpm` command not found
```bash
# Install pnpm (macOS/Linux)
curl -fsSL https://get.pnpm.io/install.sh | sh -

# Or via Homebrew (macOS)
brew install pnpm

# Or via npm if you have Node.js installed
npm install -g pnpm

# Windows
powershell -c "irm https://get.pnpm.io/install.ps1 | iex"
```

If Node.js is not installed, get it from [nodejs.org](https://nodejs.org/):
```bash
# macOS with Homebrew
brew install node

# Ubuntu/Debian
sudo apt install nodejs

# Windows - Download from nodejs.org
```

#### Python version too old
```bash
# Check current version
python --version

# Install Python 3.13+ using pyenv or your system package manager
# See https://www.python.org/downloads/
```

#### `tg-bridge` command not found after installation
```bash
# Find where uv installed the package
which python
# The tg-bridge command should be in the same bin directory

# Try running with full path
~/.venv/bin/tg-bridge

# Or activate the virtual environment
source ~/.venv/bin/activate
tg-bridge
```

#### Permission denied when installing
```bash
# Don't use sudo with uv
# If you get permission errors, try:
uv pip install -e . --user
```

### Runtime Issues

#### Bot doesn't respond
- Verify `TELEGRAM_BOT_TOKEN` is correct in `.env`
- Check `ALLOWED_USER_ID` matches your Telegram user ID (get from @userinfobot)
- Ensure bot is running (check terminal output)
- Verify bot has been started in Telegram (send `/start` to your bot)

#### API Key errors
- Check that `XAI_API_KEY` is set correctly in `.env`
- Verify the API key is valid at [x.ai](https://x.ai)
- For LangChain bot, ensure `GROQ_API_KEY` is set

#### Module not found errors
```bash
# Reinstall dependencies
uv pip install -e .
pnpm install

# Check if packages are installed
uv pip list | grep telegram
pnpm list
```

#### Bot crashes on startup
- Check `.env` file exists and has required variables
- Review terminal output for specific error messages
- Verify `WORKING_DIRECTORY` path exists and is accessible
- Check logs in `logs/tg-bridge.log` if available

### CLI doesn't start (Legacy bot only)
- Verify `CLI_COMMAND` is installed and in PATH
- Check CLI launches successfully from terminal: `<your-cli-command>`

### Output not captured (Legacy bot only)
- Adjust `PROMPT_REGEX` to match your CLI's prompt format
- Increase `CLI_TIMEOUT` for slower CLIs

### Unauthorized message
- Confirm you're messaging from the correct Telegram account
- Verify `ALLOWED_USER_ID` in `.env` matches your user ID
- Get your user ID from [@userinfobot](https://t.me/userinfobot)

## License

MIT License - see LICENSE file for details

## Contributing

Contributions welcome! Please open an issue or submit a pull request.

## Acknowledgments

Built with:
- [python-telegram-bot](https://python-telegram-bot.org/) - Telegram Bot API wrapper
- [pexpect](https://pexpect.readthedocs.io/) - Process automation
- [uv](https://github.com/astral-sh/uv) - Fast Python package manager
- [pnpm](https://pnpm.io/) - Fast, disk space efficient package manager
