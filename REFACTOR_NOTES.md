# Refactor to subprocess + stream-json

## What Changed

### Architecture Shift
**Before:** Used `pexpect` with PTY to interact with Claude CLI in interactive mode
**After:** Use `subprocess.Popen` with `claude -p` (headless mode) and `--output-format stream-json`

### Key Benefits
1. ✅ **Simpler code** - No PTY/terminal emulation complexity
2. ✅ **Structured output** - JSON lines instead of parsing raw terminal output
3. ✅ **Better reliability** - No ANSI escape codes, no prompt detection needed
4. ✅ **Proper streaming** - Built-in support from Claude Code
5. ✅ **No dangerous flags** - Use `--allowedTools` instead of `--dangerously-skip-permissions`

## Files Changed

### main.py
- Removed `pexpect` imports
- Added `json` and `subprocess` imports
- Replaced `monitor_cli_output()` with `stream_claude_output()`
- Added `read_process_lines()` async generator
- Replaced `run_claude_command()` to use subprocess with stream-json
- Added `/clear` command for conversation history
- Simplified message handling

### pyproject.toml
- Removed `pexpect>=4.9.0` dependency
- Kept only `python-dotenv` and `python-telegram-bot`

### .env.example
- Removed `PROMPT_REGEX` (no longer needed)
- Removed `CLI_TIMEOUT` (no longer needed)
- Added `ALLOWED_TOOLS` (comma-separated tool names)

## How It Works Now

### Command Format
```bash
claude -p "<prompt>" --output-format stream-json --allowedTools Tool1 Tool2 Tool3
```

### Output Format
Each line is a JSON object with a `type` field:
```json
{"type": "text", "text": "Hello! 2+2 equals 4."}
```

### Message Flow
1. User sends message to Telegram
2. Bot runs `claude -p "<message>" --output-format stream-json --allowedTools ...`
3. Bot reads stdout line by line (async)
4. Each JSON line is parsed
5. Text content is buffered and sent to Telegram in chunks
6. Process completes

### Conversation History
- Bot maintains last 5 messages in memory
- On new message, includes context: "Previous conversation:\nUser: msg1\n..."
- User can `/clear` to reset history

## Testing

### Manual Test
1. Send `/start` to your Telegram bot
2. Send a message like "hello"
3. You should receive Claude's response streamed in real-time

### Test Script
Run `./test-stream-json.py` to see Claude's raw JSON output format

### Check Logs
```bash
tail -f /tmp/tg-bridge.log
```

## Configuration

Update your `.env`:
```bash
TELEGRAM_BOT_TOKEN="your_bot_token"
ALLOWED_USER_ID="your_user_id"
CLI_COMMAND="claude"
ALLOWED_TOOLS="Bash,Read,Write,Edit,Glob,Grep"
```

## Troubleshooting

### No output from Claude
- Check logs: `tail -f /tmp/tg-bridge.log`
- Verify Claude is installed: `which claude`
- Test manually: `claude -p "hello" --output-format stream-json`

### JSON parsing errors
- Run test script to see raw output: `./test-stream-json.py`
- Check Claude Code version: `claude --version`

### Bot not responding
- Restart: `pkill -f main.py && tg-bridge`
- Check process: `ps aux | grep main.py`
