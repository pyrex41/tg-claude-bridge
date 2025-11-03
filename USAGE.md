# Telegram CLI Bridge - Usage Guide

## Quick Start

### 1. Start the Bot
```bash
tg-bridge
```

Or in background:
```bash
nohup tg-bridge > /tmp/tg-bridge.log 2>&1 &
```

### 2. Use from Telegram

Open your Telegram bot and:

1. **Send `/start`** - Initialize the bridge
2. **Send any message** - It will be processed by Claude
3. **Send `/clear`** - Clear conversation history
4. **Send `/stop`** - Stop any running Claude process

## Features

### ✅ Real-time Streaming
- Claude's responses stream to Telegram as they're generated
- No need to wait for complete response

### ✅ Conversation History
- Bot remembers your last 5 messages
- Provides context to Claude automatically
- Use `/clear` to reset

### ✅ Tool Access
- Claude can use tools you specify in `ALLOWED_TOOLS`
- Default: `Bash,Read,Write,Edit,Glob,Grep`
- Customize in `.env`

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Initialize the bot and show welcome message |
| `/stop` | Stop any running Claude process |
| `/clear` | Clear conversation history |

## Examples

### Simple Question
```
You: hello
Claude: Hello! How can I assist you today?
```

### With Context
```
You: what's 2+2?
Claude: 2+2 equals 4.

You: and what about that times 3?
Claude: 4 times 3 equals 12.
```

### Using Tools (if you allow them)
```
You: what files are in the current directory?
Claude: [Uses Bash tool to run 'ls']
Here are the files in the current directory: ...
```

## Configuration

Edit `.env`:

```bash
# Required
TELEGRAM_BOT_TOKEN="your_bot_token_from_@BotFather"
ALLOWED_USER_ID="your_telegram_user_id"

# Optional (with defaults)
CLI_COMMAND="claude"
ALLOWED_TOOLS="Bash,Read,Write,Edit,Glob,Grep"
```

## Troubleshooting

### Bot Not Responding?

1. **Check if bot is running:**
   ```bash
   ps aux | grep main.py
   ```

2. **Check logs:**
   ```bash
   tail -f /tmp/tg-bridge.log
   ```

3. **Restart bot:**
   ```bash
   pkill -f main.py
   tg-bridge
   ```

### Claude Not Working?

1. **Verify Claude is installed:**
   ```bash
   which claude
   claude --version
   ```

2. **Test Claude manually:**
   ```bash
   claude -p "hello" --output-format stream-json
   ```

### Getting Errors?

Check the logs for details:
```bash
tail -50 /tmp/tg-bridge.log
```

## Advanced Usage

### Custom Tools
Edit `.env` to allow different Claude Code tools:
```bash
ALLOWED_TOOLS="Bash,Read,Write,Edit,Glob,Grep,WebFetch,Task"
```

### Different CLI
You can bridge any CLI tool, not just Claude:
```bash
CLI_COMMAND="python my_script.py"
```

Note: This works best with tools that support `--output-format stream-json`

## Architecture

**How it works:**
1. User sends message to Telegram
2. Bot runs: `claude -p "<message>" --output-format stream-json --allowedTools ...`
3. Bot reads JSON lines from stdout
4. Text content is extracted and sent to Telegram in real-time
5. Process completes

**No complex PTY handling, no ANSI parsing - just clean JSON streaming!**

## Logs

Default log location: `/tmp/tg-bridge.log`

To change:
```bash
tg-bridge > /path/to/custom.log 2>&1
```

## Security

- Only the user specified in `ALLOWED_USER_ID` can use the bot
- Tools are restricted to what you specify in `ALLOWED_TOOLS`
- Bot runs with your user permissions
