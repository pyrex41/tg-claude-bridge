# Installation Complete! 🎉

## What Was Installed

✅ **System-wide command:** `tg-bridge`
- Location: `~/.local/bin/tg-bridge`
- Can run from **any directory**

✅ **Project files:**
- Main bot: `main.py`
- Dependencies: Managed by `uv`
- Configuration: `.env` (you need to edit this!)

✅ **Optional services:**
- macOS: `com.user.tg-cli-bridge.plist` (LaunchAgent)
- Linux: `tg-cli-bridge.service` (systemd)

## Next Steps

### 1️⃣ Configure Your Bot (REQUIRED)

Edit the `.env` file:
```bash
# From project directory
nano .env

# Or use absolute path from anywhere
nano ~/path/to/tg-claude-bridge/.env
```

**Required settings:**
```env
TELEGRAM_BOT_TOKEN="get_from_@BotFather"
ALLOWED_USER_ID="get_from_@userinfobot"
CLI_COMMAND="claude"  # or your preferred CLI
```

### 2️⃣ Get Telegram Credentials

**Bot Token:**
1. Open Telegram
2. Search for `@BotFather`
3. Send `/newbot`
4. Follow instructions
5. Copy the token

**Your User ID:**
1. Search for `@userinfobot`
2. Send `/start`
3. Copy your user ID (numeric)

### 3️⃣ Start the Bot

**From anywhere on your computer:**
```bash
tg-bridge
```

**Or in background:**
```bash
tg-bridge &
```

**Or with tmux (recommended):**
```bash
tmux new -s tg-bridge
tg-bridge
# Press Ctrl+B then D to detach
# Later: tmux attach -t tg-bridge
```

### 4️⃣ Use from Telegram

1. Find your bot (search for the name you gave it)
2. Send `/start` - launches the CLI
3. Type messages - sent to CLI
4. Send `/stop` - terminates CLI

## Optional: Auto-Start on Boot

### macOS:
```bash
cp com.user.tg-cli-bridge.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.user.tg-cli-bridge.plist
```

**Note:** Edit the `.plist` file first to update the paths if you moved the project!

### Linux:
```bash
cp tg-cli-bridge.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable tg-cli-bridge.service
systemctl --user start tg-cli-bridge.service
```

## Usage Examples

### From Terminal:
```bash
# Start bot (from anywhere)
tg-bridge

# Start in background
tg-bridge &

# With nohup (survives logout)
nohup tg-bridge > /dev/null 2>&1 &
```

### From Telegram:
```
/start          → Launches CLI (e.g., claude)
hello world     → Sent to CLI as input
/stop           → Terminates CLI
```

## Verify Installation

```bash
# Check command exists
which tg-bridge
# Should show: /Users/you/.local/bin/tg-bridge

# Check it's executable
tg-bridge --help
# Should run without errors (even if no --help implemented)

# Check PATH
echo $PATH | grep ".local/bin"
# Should show ~/.local/bin in the path
```

## Troubleshooting

**"Command not found: tg-bridge"**
```bash
# Add to PATH
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

**"TELEGRAM_BOT_TOKEN environment variable is required"**
- You need to edit `.env` with your bot credentials

**Bot doesn't respond on Telegram**
- Check bot token is correct
- Check user ID matches yours
- Check `tg-bridge` is running

**CLI doesn't start**
- Check `CLI_COMMAND` is correct in `.env`
- Test the command manually (e.g., `claude`)

## File Locations

| File | Location |
|------|----------|
| Main bot | `~/path/to/tg-claude-bridge/main.py` |
| Configuration | `~/path/to/tg-claude-bridge/.env` |
| Command symlink | `~/.local/bin/tg-bridge` |
| Logs (if service) | `~/path/to/tg-claude-bridge/logs/` |

## Uninstall

```bash
cd ~/path/to/tg-claude-bridge
./uninstall.sh
```

## Get Help

- **Quick start:** See [QUICKSTART.md](QUICKSTART.md)
- **Full guide:** See [README.md](README.md)
- **Issues:** Check logs in `logs/` directory

---

**You're all set!** 🚀

Run `tg-bridge` and start controlling your CLI from Telegram!
