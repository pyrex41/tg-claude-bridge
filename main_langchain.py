#!/usr/bin/env python3
"""
Telegram Bot with LangChain Agents
- Agent: Groq Llama 70B with coding tools (Bash, file ops, task-master CLI)
- TaskMaster: Groq Llama 70B for orchestration
"""

import os
import json
import logging
from typing import Dict, Optional, Literal
from dataclasses import dataclass
from functools import wraps

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# LangChain imports
from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.tools import ShellTool

# Load environment variables
load_dotenv()

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

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
- If Agent says "done", "completed", "what next?", or similar → Use task-master CLI to check next tasks
- If user asks "continue to next task" → Use task-master CLI to get next task and generate prompt for Agent
- For transparency: Always provide full context when asking user for decisions
- If Agent has errors/blockers → Ask user for guidance
- Always be concise in your responses

Output format (ALWAYS use valid JSON):
{{
  "action": "continue" | "ask_user",
  "prompt": "prompt for agent" | "question for user",
  "reasoning": "why you chose this action"
}}

CRITICAL: Always output ONLY valid JSON, nothing else."""


# Custom tools for Agent
@tool
def read_file(file_path: str) -> str:
    """Read contents of a file."""
    try:
        with open(file_path, 'r') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"


@tool
def write_file(file_path: str, content: str) -> str:
    """Write content to a file."""
    try:
        with open(file_path, 'w') as f:
            f.write(content)
        return f"Successfully wrote to {file_path}"
    except Exception as e:
        return f"Error writing file: {e}"


@tool
def list_directory(path: str = ".") -> str:
    """List files in a directory."""
    try:
        import os
        files = os.listdir(path)
        return "\n".join(files)
    except Exception as e:
        return f"Error listing directory: {e}"


# Initialize tools
shell_tool = ShellTool()
agent_tools = [shell_tool, read_file, write_file, list_directory]
taskmaster_tools = [shell_tool]  # TaskMaster can run task-master CLI commands

# Initialize LLMs
llm_agent = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.7,
    api_key=GROQ_API_KEY
)

llm_taskmaster = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0.3,  # Lower for decision-making
    api_key=GROQ_API_KEY
)

# Define system messages
agent_system_message = """You are a coding agent with access to tools for file operations and bash commands.

Your job is to complete coding tasks using the available tools:
- shell_tool: Run bash commands (e.g., git, npm, task-master CLI)
- read_file: Read file contents
- write_file: Write to files
- list_directory: List directory contents

Be thorough and transparent about what you're doing. Always explain your reasoning."""

# Create Agent executors using LangGraph (with correct API - just model and tools)
agent_executor = create_react_agent(
    llm_agent,
    agent_tools
)

taskmaster_executor = create_react_agent(
    llm_taskmaster,
    taskmaster_tools
)


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


async def run_agent(prompt: str, update: Update) -> str:
    """Run the Agent with LangChain and stream updates to Telegram."""
    logger.info(f"Agent processing: {prompt[:100]}...")

    # Add to conversation history
    agent_state.conversation_history.append({"role": "user", "content": prompt})

    # Invoke agent with streaming
    response_text = ""
    tool_calls = []

    try:
        # Stream agent execution (with system message)
        messages = [
            ("system", agent_system_message),
            ("user", prompt)
        ]

        async for event in agent_executor.astream({"messages": messages}):
            # Log intermediate steps for transparency
            for value in event.values():
                if "messages" in value:
                    for message in value["messages"]:
                        # Tool calls
                        if hasattr(message, 'tool_calls') and message.tool_calls:
                            for tool_call in message.tool_calls:
                                tool_name = tool_call.get('name', 'unknown')
                                await update.message.reply_text(f"🔧 Using {tool_name}")

                        # AI messages
                        if hasattr(message, 'content') and message.content:
                            content = str(message.content)
                            if content and not content.startswith('[') and len(content) > 10:
                                response_text = content
                                await update.message.reply_text(f"💭 {content[:2000]}")

    except Exception as e:
        logger.error(f"Agent error: {e}")
        response_text = f"Error: {e}"
        await update.message.reply_text(f"❌ Agent error: {e}")

    # Store and send final response
    agent_state.conversation_history.append({"role": "assistant", "content": response_text})
    agent_state.last_output = response_text

    # Keep only last 10 messages
    if len(agent_state.conversation_history) > 10:
        agent_state.conversation_history = agent_state.conversation_history[-10:]

    # Send final response
    if response_text:
        await update.message.reply_text(f"🤖 Agent final:\n{response_text[:4000]}")

    logger.info(f"Agent completed ({len(response_text)} chars)")
    return response_text


async def run_taskmaster(agent_output: str, update: Update) -> Dict:
    """Run TaskMaster to analyze Agent output and decide next action."""
    logger.info("TaskMaster analyzing agent output...")

    prompt = f"""Agent's latest output:
```
{agent_output[-1500:]}
```

Analyze this output and decide the next action. If the user asked to "continue to next task", check task-master CLI for the next task. Respond ONLY with valid JSON (no markdown, no extra text)."""

    try:
        # Invoke TaskMaster (with system message)
        messages = [
            ("system", TASKMASTER_SYSTEM_PROMPT),
            ("user", prompt)
        ]

        response = ""
        async for event in taskmaster_executor.astream({"messages": messages}):
            for value in event.values():
                if "messages" in value:
                    for message in value["messages"]:
                        # Tool calls
                        if hasattr(message, 'tool_calls') and message.tool_calls:
                            for tool_call in message.tool_calls:
                                tool_name = tool_call.get('name', 'unknown')
                                await update.message.reply_text(f"🎯 TaskMaster using: {tool_name}")

                        # AI messages
                        if hasattr(message, 'content') and message.content:
                            content = str(message.content)
                            if content:
                                response = content

        # Parse JSON decision
        decision = None
        try:
            # Try direct JSON parse
            decision = json.loads(response)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed: {e}, trying alternatives")

            # Try extracting from markdown
            try:
                if "```json" in response:
                    json_str = response.split("```json")[1].split("```")[0].strip()
                    decision = json.loads(json_str)
                elif "```" in response:
                    json_str = response.split("```")[1].split("```")[0].strip()
                    decision = json.loads(json_str)
                elif "{" in response and "}" in response:
                    # Extract JSON object
                    start = response.find("{")
                    end = response.rfind("}") + 1
                    json_str = response[start:end]
                    # Try to fix common JSON issues
                    json_str = json_str.replace("'", '"')  # Replace single quotes
                    decision = json.loads(json_str)
                else:
                    # No JSON found - make a decision based on keywords
                    response_lower = response.lower()
                    if any(word in response_lower for word in ["continue", "next", "proceed"]):
                        decision = {
                            "action": "continue",
                            "prompt": "Continue to next task",
                            "reasoning": "TaskMaster suggested continuing"
                        }
                    else:
                        decision = {
                            "action": "ask_user",
                            "prompt": f"TaskMaster responded: {response[:200]}. What should I do?",
                            "reasoning": "Could not parse JSON, asking user"
                        }
            except Exception as inner_e:
                logger.error(f"All JSON parsing attempts failed: {inner_e}")
                # Fallback to ask_user
                decision = {
                    "action": "ask_user",
                    "prompt": f"TaskMaster had trouble deciding. Response: {response[:200]}",
                    "reasoning": "JSON parsing failed"
                }

        # Send reasoning to Telegram
        reasoning = decision.get("reasoning", "No reasoning provided")
        await update.message.reply_text(f"🎯 TaskMaster: {reasoning}")

        logger.info(f"TaskMaster decision: {decision.get('action')}")
        return decision

    except Exception as e:
        logger.error(f"TaskMaster error: {e}")
        logger.error(f"Response was: {response if 'response' in locals() else 'N/A'}")
        await update.message.reply_text(f"❌ TaskMaster error: {e}")
        return {"action": "ask_user", "prompt": "Error occurred. What should I do?", "reasoning": str(e)}


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
            await update.message.reply_text(f"🔄 TaskMaster continuing:\n{next_prompt[:500]}")
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
        "🤖 **LangChain Dual-Agent Bot Started**\n\n"
        "**Two Agents:**\n"
        "🤖 Agent - Groq Llama 70B with coding tools\n"
        "🎯 TaskMaster - Orchestrates workflow\n\n"
        "**Commands:**\n"
        "/start - Initialize\n"
        "/stop - Clear agent state\n"
        "/agent - Talk to Agent\n"
        "/taskmaster - Talk to TaskMaster\n"
        "/auto on|off - Toggle auto-continue\n"
        "/clear - Clear conversation histories\n\n"
        f"**Current mode:** {active_mode}\n"
        f"**Auto-continue:** {'Enabled' if auto_continue_enabled else 'Disabled'}\n\n"
        "💡 **Tips:**\n"
        "- Say 'continue to next task' to auto-progress through tasks\n"
        "- All tool calls are shown for transparency\n"
        "- TaskMaster analyzes Agent output and decides next steps",
        parse_mode='Markdown'
    )


@require_auth
async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop all agents."""
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
        try:
            messages = [
                ("system", "You are TaskMaster - a helpful orchestration assistant. Answer questions and provide guidance."),
                ("user", message_text)
            ]

            response = ""
            async for event in taskmaster_executor.astream({"messages": messages}):
                for value in event.values():
                    if "messages" in value:
                        for message in value["messages"]:
                            if hasattr(message, 'content') and message.content:
                                response = str(message.content)
            await update.message.reply_text(f"🎯 TaskMaster:\n{response[:4000]}")
        except Exception as e:
            logger.error(f"Error in taskmaster mode: {e}")
            await update.message.reply_text(f"❌ Error: {e}")


def main():
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in .env")

    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not set in .env")

    logger.info("Starting LangChain Dual-Agent Bot...")

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
    logger.info("LangChain Dual-Agent Bot started. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
