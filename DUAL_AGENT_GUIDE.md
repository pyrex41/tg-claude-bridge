# Dual-Agent Architecture Guide

## Overview

The Telegram CLI Bridge now uses a **dual-agent architecture**:

1. **🤖 Agent** - Does actual work (runs tasks, edits files, executes commands)
2. **🎯 TaskMaster** - Orchestrates progress (decides what to do next, keeps work flowing)

Both agents run independently, maintain separate conversation histories, and both outputs are visible in your Telegram chat.

## How It Works

### Normal Flow (Auto-Continue Enabled)

```
1. You send message → Agent receives it
2. Agent does work → Streams output to Telegram
3. Agent completes → Output analyzed by TaskMaster
4. TaskMaster decides:
   - ✅ Continue? → Generates next prompt → Agent runs again (loop)
   - ❌ Need user input? → Asks you a question → Waits
```

### Example

```
You: "Work on the next task"

🤖 Agent: [Runs task-master next, gets task 1.2]
🤖 Agent: [Implements authentication feature]
🤖 Agent: [Runs tests]
🤖 Agent: "Task 1.2 complete. Tests passing."

🎯 TaskMaster: [Analyzes output]
🎯 TaskMaster: [Runs task-master next, finds task 1.3]
🎯 TaskMaster: {
  "action": "continue",
  "prompt": "Please work on task 1.3: Add user profile API",
  "reasoning": "Next task available, no blockers"
}

🔄 TaskMaster continuing: Please work on task 1.3...

🤖 Agent: [Starts working on task 1.3]
... (continues automatically)
```

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Initialize both agents |
| `/stop` | Stop all running agents immediately |
| `/agent` | Switch to talking directly with Agent |
| `/taskmaster` | Switch to talking directly with TaskMaster |
| `/auto on` | Enable auto-continue (default) |
| `/auto off` | Disable auto-continue |
| `/clear` | Clear both conversation histories |

## Modes

### Agent Mode (Default)
When you send a message, it goes to the **Agent** with auto-continue enabled.

**Good for:**
- "Work on the next task"
- "Implement feature X"
- "Fix the build"

Agent will work, then TaskMaster will decide if there's more to do.

### TaskMaster Mode
When you send a message, it goes directly to **TaskMaster** (no auto-continue).

**Good for:**
- "What should we work on next?"
- "Give me a status update"
- "What tasks are blocked?"

Switch with `/taskmaster` command.

### Manual Control
Turn off auto-continue with `/auto off` to manually control each step.

## TaskMaster Decision Logic

TaskMaster uses this prompt system:

```
Analyze Agent output and decide:
- If Agent says "done", "complete" → Check for next task
- If next task exists → action: "continue"
- If no tasks or blocked → action: "ask_user"
```

TaskMaster has access to:
- `task-master next` - Get next task
- `task-master show <id>` - Get task details
- `task-master list` - See all tasks

## Configuration

Update `.env`:

```bash
# Required
TELEGRAM_BOT_TOKEN="your_bot_token"
ALLOWED_USER_ID="your_user_id"
CLI_COMMAND="claude"

# Agent Tools (for doing work)
AGENT_TOOLS="Bash,Read,Write,Edit,Glob,Grep"

# TaskMaster Tools (for orchestration)
TASKMASTER_TOOLS="Bash(task-master *)"
```

## Use Cases

### 1. Auto-Complete All Tasks
```
/start
/auto on
"Work on the next task"

→ Agent works through all tasks automatically
→ TaskMaster keeps it going
→ You only intervene when there's a decision needed
```

### 2. Manual Step-by-Step
```
/start
/auto off
"Work on task 1.2"

→ Agent completes task
→ TaskMaster analyzes
→ You manually decide next step
```

### 3. Mixed Conversation
```
/start
"Work on task 1"

→ Agent works, TaskMaster decides to continue

/stop  (you want to check something)
/taskmaster
"What's the status of all tasks?"

→ TaskMaster gives overview

/agent
"Continue with the build"

→ Agent resumes work
```

## Both Outputs Visible

Every message in Telegram shows which agent it's from:

```
🤖 Agent: Implemented authentication...
🤖 Agent: Tests passing!

🎯 TaskMaster: Analyzed output. Next task found.
🎯 TaskMaster: {"action": "continue", ...}

🔄 TaskMaster continuing: Please work on task 1.3...

🤖 Agent: Starting task 1.3...
```

This gives you **full transparency** into what both agents are thinking and doing.

## Conversation Tracking

- **Agent conversation** = All your commands to Agent + Agent's work context
- **TaskMaster conversation** = All TaskMaster decisions + your guidance

Both maintained separately, so:
- Agent doesn't see TaskMaster's internal reasoning
- TaskMaster sees Agent output for analysis
- You see everything in Telegram

## Stopping

`/stop` command stops **both** agents immediately:
- Agent process terminated
- TaskMaster process terminated
- Auto-continue loop broken
- All in-flight work cancelled

## Advanced Usage

### Custom TaskMaster Prompt

You can talk directly to TaskMaster to override its logic:

```
/taskmaster
"Skip task 1.3 and go straight to task 2.1"

🎯 TaskMaster: [Updates its plan]

/agent
"Continue"

🤖 Agent: [Works on task 2.1]
```

### Parallel Work

With auto-continue off:

```
/auto off

"Implement feature A"
(wait for completion)

"Now implement feature B"
(wait for completion)

"Now run all tests"
```

### Emergency Stop

If agents are in an infinite loop:

```
/stop
/auto off
/agent
"What were you working on?"
```

## Architecture Benefits

✅ **Autonomous** - Can work through entire task lists
✅ **Transparent** - See both agent outputs in real-time
✅ **Controllable** - Stop, switch modes, disable auto-continue anytime
✅ **Conversational** - Talk to either agent naturally
✅ **Separate contexts** - Each agent has its own conversation history

## Logs

Check what's happening:
```bash
tail -f /tmp/tg-bridge.log
```

Look for:
- "Agent finished, consulting TaskMaster..."
- "TaskMaster decision: continue / ask_user"
- "TaskMaster continuing: ..."

## Troubleshooting

### Agents keep looping
```
/stop
/auto off
```

### TaskMaster always asks user
Check that `task-master` CLI is working:
```bash
task-master next
task-master list
```

### Can't tell agents apart
Each message has emoji prefix:
- 🤖 = Agent
- 🎯 = TaskMaster
- 🔄 = Auto-continue happening

### Want to change TaskMaster logic
Edit `TASKMASTER_SYSTEM_PROMPT` in `main.py` (lines 84-107)
