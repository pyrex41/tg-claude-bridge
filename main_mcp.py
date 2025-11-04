#!/usr/bin/env python3
"""
Telegram Bot with Dual MCP-based Agents
Uses Zen MCP server for Agent and TaskMaster interactions
"""

import os
import json
import asyncio
import logging
from typing import Dict, Optional, Literal
from dataclasses import dataclass, field
from functools import wraps

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Load environment variables
load_dotenv()

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID"))
AGENT_MODEL = os.getenv("AGENT_MODEL", "claude-sonnet-4-5-20250929")
TASKMASTER_MODEL = os.getenv("TASKMASTER_MODEL", "claude-sonnet-4-5-20250929")

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global state
@dataclass
class AgentState:
    """State for a single MCP-based agent."""
    continuation_id: Optional[str] = None
    conversation_history: list = field(default_factory=list)
    last_output: str = ""

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


async def call_mcp_chat(
    prompt: str,
    model: str,
    continuation_id: Optional[str] = None,
    working_dir: str = os.getcwd()
) -> Dict:
    """
    Call the mcp__zen__chat tool.

    Returns dict with:
    - response: The AI's response text
    - continuation_id: ID for continuing the conversation
    """
    # Import MCP client here
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "task-master-ai"],
        env=dict(os.environ)  # Pass all environment variables
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Prepare tool call arguments
            args = {
                "prompt": prompt,
                "working_directory_absolute_path": working_dir,
                "model": model
            }

            if continuation_id:
                args["continuation_id"] = continuation_id

            # Call the chat tool
            result = await session.call_tool("mcp__zen__chat", arguments=args)

            # Extract response
            response_text = ""
            new_continuation_id = None

            if result.content:
                for content in result.content:
                    if hasattr(content, 'text'):
                        response_text += content.text
                    # Look for continuation_id in response
                    if hasattr(content, 'continuation_id'):
                        new_continuation_id = content.continuation_id

            return {
                "response": response_text,
                "continuation_id": new_continuation_id or continuation_id
            }


async def run_agent(prompt: str, update: Update) -> str:
    """Run the Agent and return its response."""
    global agent_state

    logger.info(f"Agent processing: {prompt[:100]}...")

    try:
        result = await call_mcp_chat(
            prompt=prompt,
            model=AGENT_MODEL,
            continuation_id=agent_state.continuation_id
        )

        response = result["response"]
        agent_state.continuation_id = result["continuation_id"]
        agent_state.last_output = response

        # Send to Telegram
        await update.message.reply_text(f"🤖 Agent:\n{response[:4000]}")

        logger.info(f"Agent responded ({len(response)} chars)")
        return response

    except Exception as e:
        logger.error(f"Error running agent: {e}")
        await update.message.reply_text(f"❌ Agent error: {e}")
        return ""


async def run_taskmaster(agent_output: str, update: Update) -> Dict:
    """Run TaskMaster to decide next action."""
    global taskmaster_state

    logger.info("TaskMaster analyzing agent output...")

    prompt = f"""{TASKMASTER_SYSTEM_PROMPT}

Agent's latest output:
```
{agent_output[-1500:]}  # Last 1500 chars
```

Analyze this output and decide the next action. Respond ONLY with valid JSON."""

    try:
        result = await call_mcp_chat(
            prompt=prompt,
            model=TASKMASTER_MODEL,
            continuation_id=taskmaster_state.continuation_id
        )

        response = result["response"]
        taskmaster_state.continuation_id = result["continuation_id"]

        # Parse JSON decision
        try:
            decision = json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
                decision = json.loads(json_str)
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
                decision = json.loads(json_str)
            else:
                raise

        # Send TaskMaster reasoning to Telegram
        reasoning = decision.get("reasoning", "No reasoning provided")
        await update.message.reply_text(f"🎯 TaskMaster: {reasoning}")

        logger.info(f"TaskMaster decision: {decision.get('action')}")
        return decision

    except Exception as e:
        logger.error(f"Error running taskmaster: {e}")
        await update.message.reply_text(f"❌ TaskMaster error: {e}")
        return {"action": "ask_user", "prompt": "Error occurred. What should I do?"}


async def run_agent_with_auto_continue(prompt: str, update: Update, depth: int = 0):
    """Run agent and auto-continue based on TaskMaster decisions."""
    global auto_continue_enabled

    if depth > 10:
        await update.message.reply_text("⚠️ Auto-continue depth limit reached (10). Stopping.")
        return

    # Run the agent
    agent_output = await run_agent(prompt, update)
    if not agent_output:
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
        "🤖 Agent - Does work with tools\n"
        "🎯 TaskMaster - Orchestrates and decides next steps\n\n"
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
    """Stop all agents (clear continuation IDs)."""
    global agent_state, taskmaster_state
    agent_state.continuation_id = None
    taskmaster_state.continuation_id = None
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
        try:
            result = await call_mcp_chat(
                prompt=message_text,
                model=TASKMASTER_MODEL,
                continuation_id=taskmaster_state.continuation_id
            )
            response = result["response"]
            taskmaster_state.continuation_id = result["continuation_id"]
            await update.message.reply_text(f"🎯 TaskMaster:\n{response[:4000]}")
        except Exception as e:
            logger.error(f"Error in taskmaster mode: {e}")
            await update.message.reply_text(f"❌ Error: {e}")


def main():
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in .env")

    logger.info("Starting Dual-Agent MCP Bot...")

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
    logger.info("Dual-Agent MCP Bot started. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
