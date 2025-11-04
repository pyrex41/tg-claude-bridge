#!/usr/bin/env python3
"""
Telegram Bot with Hybrid AI Agents
- Agent: Uses Claude Code SDK (via claude login)
- TaskMaster: Uses Groq API (llama-3.3-70b)
"""

import os
import json
import subprocess
import asyncio
import logging
from typing import Dict, Optional, Literal
from dataclasses import dataclass
from functools import wraps

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Load environment variables
load_dotenv()

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global state
@dataclass
class AgentState:
    """State for tracking agent conversations."""
    conversation_history: list
    last_output: str = ""

    def __init__(self):
        self.conversation_history = []
        self.last_output = ""

agent_state = AgentState()
taskmaster_state = AgentState()
auto_continue_enabled = True
active_mode: Literal["agent", "taskmaster"] = "agent"

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


async def call_claude_sdk(prompt: str, tools: list = None) -> str:
    """
    Call Claude using the TypeScript SDK bridge.
    Uses your existing 'claude login' authentication.
    """
    try:
        cmd = ["node", "claude-bridge.js", prompt]

        if tools:
            cmd.append(f"--tools={','.join(tools)}")

        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await result.communicate()

        if result.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            logger.error(f"Claude SDK error: {error_msg}")
            return f"Error: {error_msg}"

        response = json.loads(stdout.decode())
        return response.get("response", "No response")

    except Exception as e:
        logger.error(f"Error calling Claude SDK: {e}")
        return f"Error: {e}"


async def call_groq(prompt: str, system_prompt: str = "") -> str:
    """
    Call Groq API using llama-3.3-70b-versatile.
    Fast and free alternative for TaskMaster orchestration.
    """
    if not GROQ_API_KEY:
        return "Error: GROQ_API_KEY not set in .env"

    try:
        # Use curl for simplicity (or install groq Python SDK)
        import aiohttp

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 2000
                }
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"Groq API error: {error_text}")
                    return f"Error: {error_text}"

                data = await resp.json()
                return data["choices"][0]["message"]["content"]

    except Exception as e:
        logger.error(f"Error calling Groq: {e}")
        return f"Error: {e}"


async def run_agent(prompt: str, update: Update) -> str:
    """Run the Agent using Claude SDK."""
    logger.info(f"Agent processing: {prompt[:100]}...")

    # Add to conversation history
    agent_state.conversation_history.append({"role": "user", "content": prompt})

    # Call Claude with tools
    tools = ["Bash", "Read", "Write", "Edit", "Glob", "Grep"]
    response = await call_claude_sdk(prompt, tools=tools)

    agent_state.conversation_history.append({"role": "assistant", "content": response})
    agent_state.last_output = response

    # Keep only last 10 messages
    if len(agent_state.conversation_history) > 10:
        agent_state.conversation_history = agent_state.conversation_history[-10:]

    # Send to Telegram
    await update.message.reply_text(f"🤖 Agent:\n{response[:4000]}")

    logger.info(f"Agent responded ({len(response)} chars)")
    return response


async def run_taskmaster(agent_output: str, update: Update) -> Dict:
    """Run TaskMaster using Groq API to decide next action."""
    logger.info("TaskMaster analyzing agent output...")

    prompt = f"""Agent's latest output:
```
{agent_output[-1500:]}  # Last 1500 chars
```

Analyze this output and decide the next action. Respond ONLY with valid JSON."""

    response = await call_groq(prompt, system_prompt=TASKMASTER_SYSTEM_PROMPT)

    # Parse JSON decision
    try:
        # Try to extract JSON from response
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0].strip()
            decision = json.loads(json_str)
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0].strip()
            decision = json.loads(json_str)
        else:
            decision = json.loads(response)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse TaskMaster response as JSON: {e}")
        logger.error(f"Response was: {response}")
        decision = {"action": "ask_user", "prompt": "Error parsing TaskMaster response. What should I do?"}

    # Send TaskMaster reasoning to Telegram
    reasoning = decision.get("reasoning", "No reasoning provided")
    await update.message.reply_text(f"🎯 TaskMaster: {reasoning}")

    logger.info(f"TaskMaster decision: {decision.get('action')}")
    return decision


async def run_agent_with_auto_continue(prompt: str, update: Update, depth: int = 0):
    """Run agent and auto-continue based on TaskMaster decisions."""
    global auto_continue_enabled

    if depth > 10:
        await update.message.reply_text("⚠️ Auto-continue depth limit reached (10). Stopping.")
        return

    # Run the agent
    agent_output = await run_agent(prompt, update)
    if not agent_output or agent_output.startswith("Error:"):
        return

    # If auto-continue is disabled, stop here
    if not auto_continue_enabled:
        logger.info("Auto-continue disabled, stopping")
        return

    # Consult TaskMaster
    decision = await run_taskmaster(agent_output, update)

    if decision.get("action") == "continue":
        next_prompt = decision.get("prompt", "")
        if next_prompt:
            await update.message.reply_text(f"🔄 TaskMaster continuing: {next_prompt[:200]}")
            # Recursive call with increased depth
            await run_agent_with_auto_continue(next_prompt, update, depth + 1)
    elif decision.get("action") == "ask_user":
        question = decision.get("prompt", "What next?")
        await update.message.reply_text(f"❓ {question}")


# Command handlers
@require_auth
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initialize the bot."""
    await update.message.reply_text(
        "🤖 Dual-Agent Bridge Started\n\n"
        "**Two Agents:**\n"
        "🤖 Agent - Uses Claude Code (via claude login)\n"
        "🎯 TaskMaster - Uses Groq Llama 70B (orchestration)\n\n"
        "**Commands:**\n"
        "/start - Initialize\n"
        "/stop - Stop all agents\n"
        "/agent - Talk to Agent\n"
        "/taskmaster - Talk to TaskMaster\n"
        "/auto on|off - Toggle auto-continue\n"
        "/clear - Clear conversation histories\n\n"
        f"**Current mode:** {active_mode}\n"
        f"**Auto-continue:** {'Enabled' if auto_continue_enabled else 'Disabled'}"
    )


@require_auth
async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop all agents (clear conversations)."""
    global agent_state, taskmaster_state
    agent_state = AgentState()
    taskmaster_state = AgentState()
    await update.message.reply_text("⏹️ All agents stopped (conversations cleared)")


@require_auth
async def cmd_agent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch to Agent mode."""
    global active_mode
    active_mode = "agent"
    await update.message.reply_text("🤖 Now talking to: Agent")


@require_auth
async def cmd_taskmaster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch to TaskMaster mode."""
    global active_mode
    active_mode = "taskmaster"
    await update.message.reply_text("🎯 Now talking to: TaskMaster")


@require_auth
async def cmd_auto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle auto-continue."""
    global auto_continue_enabled

    if context.args and len(context.args) > 0:
        arg = context.args[0].lower()
        if arg == "on":
            auto_continue_enabled = True
            await update.message.reply_text("✅ Auto-continue: Enabled")
        elif arg == "off":
            auto_continue_enabled = False
            await update.message.reply_text("✅ Auto-continue: Disabled")
        else:
            await update.message.reply_text("Usage: /auto on|off")
    else:
        await update.message.reply_text(f"Auto-continue: {'Enabled' if auto_continue_enabled else 'Disabled'}")


@require_auth
async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear both conversation histories."""
    global agent_state, taskmaster_state
    agent_state = AgentState()
    taskmaster_state = AgentState()
    await update.message.reply_text("🗑️ Both conversation histories cleared")


@require_auth
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user messages."""
    global active_mode

    message_text = update.message.text
    logger.info(f"Message for {active_mode}: {message_text}")

    if active_mode == "agent":
        # Send to agent with auto-continue
        await run_agent_with_auto_continue(message_text, update)
    else:  # taskmaster
        # Talk directly to TaskMaster
        response = await call_groq(message_text)
        await update.message.reply_text(f"🎯 TaskMaster:\n{response[:4000]}")


def main():
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in .env")

    if not GROQ_API_KEY:
        logger.warning("GROQ_API_KEY not set - TaskMaster will not work!")

    logger.info("Starting Dual-Agent Bot (Claude SDK + Groq)...")

    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("stop", cmd_stop))
    application.add_handler(CommandHandler("agent", cmd_agent))
    application.add_handler(CommandHandler("taskmaster", cmd_taskmaster))
    application.add_handler(CommandHandler("auto", cmd_auto))
    application.add_handler(CommandHandler("clear", cmd_clear))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start bot
    logger.info("Dual-Agent Bot started. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
