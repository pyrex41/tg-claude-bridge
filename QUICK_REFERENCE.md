# Quick Reference - Dual-Agent Telegram Bridge

## 🚀 Quick Start

```bash
# Start bot
tg-bridge

# Or in background
nohup tg-bridge > /tmp/tg-bridge.log 2>&1 &
```

## 📱 Telegram Commands

```
/start          → Initialize both agents
/stop           → Stop all agents
/agent          → Talk to Agent (work executor)
/taskmaster     → Talk to TaskMaster (orchestrator)
/auto on|off    → Toggle auto-continue
/clear          → Clear conversations
```

## 💬 Quick Workflows

### Auto-Complete Tasks
```
/start
"Work on the next task"
→ Agents automatically work through all tasks
```

### Manual Control
```
/start
/auto off
"Work on task 1.2"
→ Agent works, waits for your next command
```

### Get Status
```
/taskmaster
"What tasks are left?"
→ TaskMaster checks and responds
```

### Emergency Stop
```
/stop
→ Stops both agents immediately
```

## 🤖 Understanding Output

```
🤖 Agent: ...        → Work being done
🎯 TaskMaster: ...   → Orchestration decision
🔄 Continuing...     → Auto-continue triggered
```

## ⚙️ Configuration (.env)

```bash
TELEGRAM_BOT_TOKEN="your_token"
ALLOWED_USER_ID="123456789"
AGENT_TOOLS="Bash,Read,Write,Edit,Glob,Grep"
TASKMASTER_TOOLS="Bash(task-master *)"
```

## 🔍 Check Logs

```bash
tail -f /tmp/tg-bridge.log
```

## 🎯 TaskMaster Decides:

- ✅ **Continue** → Generates next prompt for Agent
- ❌ **Ask User** → Waits for your decision

## 📊 Architecture Flow

```
You → Agent → Work → Output
         ↓
   TaskMaster → Decision
         ↓
   Continue? → Agent (loop)
   OR
   Ask User? → Wait
```

## 🛠️ Troubleshooting

| Problem | Solution |
|---------|----------|
| Infinite loop | `/stop` then `/auto off` |
| Agent not responding | Check logs: `tail /tmp/tg-bridge.log` |
| Can't tell agents apart | Look for 🤖 (Agent) vs 🎯 (TaskMaster) |
| Want to change mode | Use `/agent` or `/taskmaster` |
