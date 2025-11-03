# Quick Start Guide

## Installation (5 minutes)

```bash
# 1. Clone and install
git clone <repo-url>
cd tg-claude-bridge
./install.sh

# 2. Add to PATH (if not already)
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

## Configuration (2 minutes)

```bash
# 1. Get Telegram bot token from @BotFather
# 2. Get your user ID from @userinfobot
# 3. Edit .env file
nano .env  # or vim, code, etc.
```

Set these variables:
```env
TELEGRAM_BOT_TOKEN="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
ALLOWED_USER_ID="123456789"
CLI_COMMAND="claude"
```

## Usage

### From anywhere on your computer:

```bash
tg-bridge
```

That's it! The bot is now running.

### From Telegram:

1. Find your bot on Telegram (search for the name you gave it)
2. Send `/start` - launches your CLI
3. Type messages - they get sent to the CLI
4. Send `/stop` - terminates the CLI session

## Run on System Startup (macOS)

```bash
# One-time setup
cp com.user.tg-cli-bridge.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.user.tg-cli-bridge.plist
```

Now it will auto-start when you log in!

## Troubleshooting

**Bot doesn't respond:**
- Check your bot token and user ID in `.env`
- Make sure `tg-bridge` is running (check terminal)

**Can't run `tg-bridge` command:**
- Verify `~/.local/bin` is in your PATH: `echo $PATH`
- Run `. ~/.zshrc` or `. ~/.bashrc` to reload shell

**CLI doesn't start:**
- Check that your CLI_COMMAND is correct and in PATH
- Try running it manually: `claude` (or whatever you set)

## Tips

- **Leave it running:** Open a dedicated terminal window for `tg-bridge`
- **Use tmux/screen:** Run in background with `tmux` or `screen`
- **Auto-start:** Use LaunchAgent (macOS) or systemd (Linux) as shown above
- **Check logs:** Look in `logs/` directory for debugging

## Common Commands

```bash
tg-bridge              # Start the bridge
tg-bridge &            # Run in background
fg                     # Bring background job to foreground (Ctrl+Z then 'bg' to background again)
```

## Next Steps

- See full [README.md](README.md) for advanced configuration
- Customize `PROMPT_REGEX` for different CLI tools
- Adjust `CLI_TIMEOUT` for slower operations
