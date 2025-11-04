#!/usr/bin/env python3
"""
Telegram CLI Bridge Bot - Dual Agent Architecture

Agent Model: Does actual work with Claude Code + tools
TaskMaster Model: Orchestrates progress, decides next steps

Both agents maintained in separate conversations, both outputs visible in Telegram.
"""

import os
import sys
import logging
import json
import asyncio
import subprocess
from typing import Optional, Dict, List, Literal
from functools import wraps
from dataclasses import dataclass

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Load environment variables
load_dotenv()

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = os.getenv("ALLOWED_USER_ID")
CLI_COMMAND = os.getenv("CLI_COMMAND", "claude")
AGENT_TOOLS = os.getenv("AGENT_TOOLS", "Bash,Read,Write,Edit,Glob,Grep")
TASKMASTER_TOOLS = os.getenv("TASKMASTER_TOOLS", "Bash(task-master *)")

# Validate required environment variables
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
if not ALLOWED_USER_ID:
    raise ValueError("ALLOWED_USER_ID environment variable is required")

ALLOWED_USER_ID = int(ALLOWED_USER_ID)

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Reduce noise from httpx and telegram libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.INFO)


@dataclass
class AgentState:
    """State for a single agent (Agent or TaskMaster)."""
    process: Optional[subprocess.Popen] = None
    stream_task: Optional[asyncio.Task] = None
    conversation_history: List[str] = None
    last_output: str = ""

    def __post_init__(self):
        if self.conversation_history is None:
            self.conversation_history = []


# Global state
current_chat_id: Optional[int] = None
agent_state = AgentState()
taskmaster_state = AgentState()
auto_continue_enabled = True  # TaskMaster auto-continuation
active_mode: Literal["agent", "taskmaster"] = "agent"  # Who user is talking to


TASKMASTER_SYSTEM_PROMPT = """You are TaskMaster - an orchestration agent that keeps projects moving forward.

Your job:
1. Analyze the Agent's output
2. Determine if work is complete or needs continuation
3. Either:
   a) Generate the next prompt for the Agent to continue work
   b) Ask the user for a decision if blocked

Guidelines:
- If Agent says "done", "completed", "what next?", or similar → Check if there are more tasks
- Use task-master CLI to check next tasks: "task-master next"
- If next task exists → Generate prompt: "Please work on task X: [description]"
- If no tasks or unclear → Ask user: "Agent completed X. What would you like to do next?"
- If Agent has errors/blockers → Ask user for guidance
- Always be concise in your responses

Output format (JSON):
{
  "action": "continue" | "ask_user",
  "prompt": "prompt for agent" | "question for user",
  "reasoning": "why you chose this action"
}
"""


def require_auth(func):
    """Decorator to restrict access to authorized user only."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id != ALLOWED_USER_ID:
            logger.warning(f"Unauthorized access attempt from user {user_id}")
            await update.message.reply_text("Unauthorized")
            return
        return await func(update, context)
    return wrapper


async def stream_output(
    process: subprocess.Popen,
    application,
    chat_id: int,
    agent_name: str,
    state: AgentState
):
    """Stream agent output and send to Telegram in real-time."""
    logger.info(f"Starting {agent_name} output stream monitor")

    try:
        buffer = ""
        full_output = ""

        async for line in read_process_lines(process):
            if not line.strip():
                continue

            try:
                # Parse JSON line
                data = json.loads(line)
                logger.debug(f"{agent_name} JSON: {data.get('type', 'unknown')}")

                # Extract text content
                text = None
                if data.get("type") == "assistant":
                    # Handle assistant message type from stream-json
                    message = data.get("message", {})
                    content = message.get("content", [])
                    if isinstance(content, list) and len(content) > 0:
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                text = item.get("text", "")
                                break
                elif data.get("type") == "text":
                    text = data.get("text", "")
                elif data.get("type") == "message":
                    content = data.get("content", {})
                    if isinstance(content, dict):
                        text = content.get("text", "")
                    elif isinstance(content, str):
                        text = content

                # Accumulate output
                if text and text.strip():
                    buffer += text
                    full_output += text

                    # Send chunks when we have enough content
                    if len(buffer) > 100 or "\n\n" in buffer:
                        try:
                            # Add emoji prefix to distinguish agents
                            prefix = "🤖 Agent: " if agent_name == "Agent" else "🎯 TaskMaster: "
                            await application.bot.send_message(
                                chat_id=chat_id,
                                text=prefix + buffer[:4000]
                            )
                            logger.info(f"Sent {len(buffer)} chars from {agent_name}")
                            buffer = ""
                        except Exception as e:
                            logger.error(f"Error sending message: {e}")

            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON: {e}")
                continue
            except Exception as e:
                logger.error(f"Error processing stream line: {e}")
                continue

        # Send any remaining buffered text
        if buffer.strip():
            try:
                prefix = "🤖 Agent: " if agent_name == "Agent" else "🎯 TaskMaster: "
                await application.bot.send_message(
                    chat_id=chat_id,
                    text=prefix + buffer[:4000]
                )
            except Exception as e:
                logger.error(f"Error sending final buffer: {e}")

        # Store full output
        state.last_output = full_output

    except Exception as e:
        logger.error(f"{agent_name} stream monitor error: {e}")
    finally:
        logger.info(f"{agent_name} output stream ended")


async def read_process_lines(process: subprocess.Popen):
    """Async generator to read lines from subprocess stdout."""
    loop = asyncio.get_event_loop()

    while True:
        line = await loop.run_in_executor(None, process.stdout.readline)
        if not line:
            break
        yield line


def run_agent_command(prompt: str, agent_type: Literal["agent", "taskmaster"]) -> subprocess.Popen:
    """Run Claude Code for either Agent or TaskMaster."""
    if agent_type == "agent":
        tools = AGENT_TOOLS.split(",")
    else:
        tools = TASKMASTER_TOOLS.split(",")

    command = [
        CLI_COMMAND,
        "-p", prompt,
        "--output-format", "stream-json",
        "--allowedTools"
    ] + tools

    logger.info(f"Running {agent_type}: {' '.join(command[:3])}...")

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )

    return process


async def run_taskmaster_decision(agent_output: str, application, chat_id: int) -> Dict:
    """Run TaskMaster to decide next action."""
    global taskmaster_state

    prompt = f"""{TASKMASTER_SYSTEM_PROMPT}

Agent's latest output:
```
{agent_output[-1500:]}  # Last 1500 chars
```

Analyze this output and decide the next action. Respond ONLY with valid JSON.
"""

    # Stop any existing TaskMaster process
    if taskmaster_state.process and taskmaster_state.process.poll() is None:
        taskmaster_state.process.terminate()

    # Run TaskMaster
    taskmaster_state.process = run_agent_command(prompt, "taskmaster")

    # Stream output
    taskmaster_state.stream_task = asyncio.create_task(
        stream_output(
            taskmaster_state.process,
            application,
            chat_id,
            "TaskMaster",
            taskmaster_state
        )
    )

    # Wait for completion
    await taskmaster_state.stream_task

    # Parse TaskMaster's decision from output
    try:
        # Try to extract JSON from output
        output = taskmaster_state.last_output
        # Find JSON block
        if "{" in output and "}" in output:
            start = output.find("{")
            end = output.rfind("}") + 1
            json_str = output[start:end]
            decision = json.loads(json_str)
            return decision
        else:
            # Fallback: assume need to ask user
            return {
                "action": "ask_user",
                "prompt": "TaskMaster output was unclear. What would you like to do next?",
                "reasoning": "Could not parse TaskMaster response"
            }
    except Exception as e:
        logger.error(f"Error parsing TaskMaster decision: {e}")
        return {
            "action": "ask_user",
            "prompt": "I need your guidance on what to do next.",
            "reasoning": f"Error: {e}"
        }


async def run_agent_with_auto_continue(prompt: str, application, chat_id: int):
    """Run Agent and automatically continue if TaskMaster says so."""
    global agent_state, auto_continue_enabled

    # Run Agent
    if agent_state.conversation_history is not None: agent_state.conversation_history.append(prompt)
    agent_state.process = run_agent_command(prompt, "agent")

    agent_state.stream_task = asyncio.create_task(
        stream_output(
            agent_state.process,
            application,
            chat_id,
            "Agent",
            agent_state
        )
    )

    # Wait for Agent to complete
    await agent_state.stream_task

    # If auto-continue enabled, ask TaskMaster what to do
    if auto_continue_enabled and agent_state.last_output:
        logger.info("Agent finished, consulting TaskMaster...")

        decision = await run_taskmaster_decision(
            agent_state.last_output,
            application,
            chat_id
        )

        logger.info(f"TaskMaster decision: {decision.get('action')}")

        if decision.get("action") == "continue":
            # TaskMaster wants to continue - run Agent again
            next_prompt = decision.get("prompt", "")
            if next_prompt:
                await application.bot.send_message(
                    chat_id=chat_id,
                    text=f"🔄 TaskMaster continuing: {next_prompt[:200]}..."
                )
                # Recursive call to continue
                await run_agent_with_auto_continue(next_prompt, application, chat_id)
        else:
            # TaskMaster wants user input - already sent question
            pass


@require_auth
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    global current_chat_id, agent_state, taskmaster_state, active_mode

    current_chat_id = update.effective_chat.id
    agent_state = AgentState()
    taskmaster_state = AgentState()
    active_mode = "agent"

    await update.message.reply_text(
        "🤖 Dual-Agent Bridge Started\n\n"
        "**Two Agents:**\n"
        "🤖 Agent - Does work with tools\n"
        "🎯 TaskMaster - Orchestrates progress\n\n"
        "**Commands:**\n"
        "/start - Initialize\n"
        "/stop - Stop all agents\n"
        "/agent - Talk to Agent\n"
        "/taskmaster - Talk to TaskMaster\n"
        "/auto on|off - Toggle auto-continue\n"
        "/clear - Clear conversation\n\n"
        "**Current mode:** Agent\n"
        "**Auto-continue:** Enabled"
    )


@require_auth
async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stop all running processes."""
    global agent_state, taskmaster_state

    stopped = []

    # Stop Agent
    if agent_state.process and agent_state.process.poll() is None:
        agent_state.process.terminate()
        agent_state.process = None
        stopped.append("Agent")

    if agent_state.stream_task and not agent_state.stream_task.done():
        agent_state.stream_task.cancel()
        agent_state.stream_task = None

    # Stop TaskMaster
    if taskmaster_state.process and taskmaster_state.process.poll() is None:
        taskmaster_state.process.terminate()
        taskmaster_state.process = None
        stopped.append("TaskMaster")

    if taskmaster_state.stream_task and not taskmaster_state.stream_task.done():
        taskmaster_state.stream_task.cancel()
        taskmaster_state.stream_task = None

    if stopped:
        await update.message.reply_text(f"❌ Stopped: {', '.join(stopped)}")
    else:
        await update.message.reply_text("No agents running.")


@require_auth
async def agent_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Switch to talking to Agent."""
    global active_mode
    active_mode = "agent"
    await update.message.reply_text("🤖 Now talking to: Agent")


@require_auth
async def taskmaster_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Switch to talking to TaskMaster."""
    global active_mode
    active_mode = "taskmaster"
    await update.message.reply_text("🎯 Now talking to: TaskMaster")


@require_auth
async def auto_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle auto-continue mode."""
    global auto_continue_enabled

    if context.args and len(context.args) > 0:
        arg = context.args[0].lower()
        if arg in ["on", "true", "1", "yes"]:
            auto_continue_enabled = True
            await update.message.reply_text("✅ Auto-continue: Enabled")
        elif arg in ["off", "false", "0", "no"]:
            auto_continue_enabled = False
            await update.message.reply_text("❌ Auto-continue: Disabled")
        else:
            await update.message.reply_text("Usage: /auto on|off")
    else:
        status = "Enabled" if auto_continue_enabled else "Disabled"
        await update.message.reply_text(f"Auto-continue: {status}\n\nUsage: /auto on|off")


@require_auth
async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear conversation history."""
    global agent_state, taskmaster_state

    agent_state.conversation_history = []
    taskmaster_state.conversation_history = []
    await update.message.reply_text("🗑️ Cleared both conversation histories")


@require_auth
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages - route to appropriate agent."""
    global current_chat_id, active_mode

    user_input = update.message.text or ''
    logger.info(f"Message for {active_mode}: {user_input}")

    if current_chat_id is None:
        current_chat_id = update.effective_chat.id if update.effective_chat else None

    try:
        if active_mode == "agent":
            # Send to Agent with auto-continue
            await run_agent_with_auto_continue(user_input, context.application, current_chat_id)
        else:
            # Send to TaskMaster directly (no auto-continue)
            if taskmaster_state.conversation_history is not None: taskmaster_state.conversation_history.append(user_input or '')

            # Build prompt with context
            if len(taskmaster_state.conversation_history) > 1:
                context_msgs = taskmaster_state.conversation_history[-5:]
                prompt = "Previous:\n" + "\n".join(f"User: {m}" for m in context_msgs[:-1])
                prompt += f"\n\nCurrent:\n{user_input}"
            else:
                prompt = user_input

            taskmaster_state.process = run_agent_command(prompt, "taskmaster")

            taskmaster_state.stream_task = asyncio.create_task(
                stream_output(
                    taskmaster_state.process,
                    context.application,
                    current_chat_id,
                    "TaskMaster",
                    taskmaster_state
                )
            )

    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors."""
    logger.error(f"Update {update} caused error: {context.error}")


def main() -> None:
    """Start the bot."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("agent", agent_command))
    application.add_handler(CommandHandler("taskmaster", taskmaster_command))
    application.add_handler(CommandHandler("auto", auto_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.add_error_handler(error_handler)

    logger.info("Dual-Agent Bot started. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
