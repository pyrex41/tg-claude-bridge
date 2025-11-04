#!/usr/bin/env python3
"""
Autonomous Task-Master Bot with OpenCode
Iterates through task-master tasks autonomously with full transparency
"""

import os
import logging
from typing import Optional
from dataclasses import dataclass
from functools import wraps

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from opencode_agent import OpenCodeAgent
from task_master_client import TaskMasterClient, Task

# Load environment
load_dotenv()

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID"))
OPENCODE_MODEL = os.getenv("OPENCODE_MODEL", "grok-4-non-reasoning")
WORKING_DIRECTORY = os.getenv("WORKING_DIRECTORY", os.getcwd())
AUTO_CONTINUE = os.getenv("AUTO_CONTINUE", "true").lower() == "true"
REQUIRE_APPROVAL = os.getenv("REQUIRE_APPROVAL", "false").lower() == "true"

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global state
@dataclass
class BotState:
    """Bot state management."""
    agent: OpenCodeAgent
    task_client: TaskMasterClient
    current_task: Optional[Task] = None
    paused: bool = False
    auto_continue: bool = AUTO_CONTINUE

    def __post_init__(self):
        if self.agent is None:
            self.agent = OpenCodeAgent(model=OPENCODE_MODEL, working_dir=WORKING_DIRECTORY)
        if self.task_client is None:
            self.task_client = TaskMasterClient(working_dir=WORKING_DIRECTORY)

bot_state = BotState(
    agent=OpenCodeAgent(model=OPENCODE_MODEL, working_dir=WORKING_DIRECTORY),
    task_client=TaskMasterClient(working_dir=WORKING_DIRECTORY)
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


async def work_on_task(task: Task, update: Update) -> bool:
    """
    Work on a specific task using OpenCode agent.

    Returns True if task completed successfully, False otherwise.
    """
    logger.info(f"Working on task {task.id}: {task.title}")

    # Update status
    await bot_state.task_client.mark_in_progress(task.id)
    await update.message.reply_text(
        f"🚀 **Starting work on task {task.id}**\n"
        f"**Title:** {task.title}\n"
        f"**Description:** {task.description[:200]}"
    )

    # Create comprehensive prompt for the agent
    prompt = f"""I need you to work on the following task:

**Task ID:** {task.id}
**Title:** {task.title}
**Description:** {task.description}

Please:
1. Analyze what needs to be done
2. Break it down into steps
3. Execute each step
4. Verify completion
5. Report back with results

Be thorough and transparent about what you're doing. Use tools as needed.
"""

    try:
        # Create event callback to send updates to Telegram
        async def send_event(event):
            """Send parsed event to Telegram."""
            # Only send meaningful events to avoid spam
            if event.type in ['tool', 'file', 'error', 'step']:
                try:
                    await update.message.reply_text(event.message)
                except Exception as e:
                    logger.error(f"Failed to send event: {e}")

        # Run OpenCode agent with event streaming
        response = await bot_state.agent.run(
            prompt=prompt,
            continue_session=True,
            event_callback=send_event
        )

        # Send agent's final response to Telegram
        if response.content and len(response.content) > 20:
            await update.message.reply_text(
                f"🤖 **Agent:**\n{response.content[:4000]}"
            )

        # Check if task appears complete
        # Look for completion indicators
        completion_indicators = [
            "completed", "finished", "done", "success", "successful",
            "implemented", "all tests pass", "verified", "created", "added"
        ]

        content_lower = response.content.lower()
        seems_complete = any(indicator in content_lower for indicator in completion_indicators)

        # Check for error indicators
        error_indicators = [
            "error", "failed", "blocked", "cannot", "unable", "need help",
            "couldn't", "didn't work", "issue"
        ]

        has_errors = any(indicator in content_lower for indicator in error_indicators)

        # Check tool usage - if tools were used successfully, likely made progress
        used_tools = len(response.tool_calls) > 0

        # Decision logic
        if has_errors:
            # Has errors - ask AI to analyze and provide guidance
            await update.message.reply_text(
                f"⚠️ **Agent encountered issues**\n"
                "Analyzing response..."
            )

            # Use a quick AI call to decide what to do next
            analysis_prompt = f"""The agent was working on: {task.title}

Agent's response:
{response.content[:1000]}

The response indicates errors or issues. Should we:
A) Retry with additional guidance
B) Mark as blocked and move to next task
C) The errors were handled, continue

Respond with just the letter (A, B, or C) and a brief reason."""

            analysis = await bot_state.agent.run(analysis_prompt, continue_session=False)
            decision = analysis.content.strip()

            await update.message.reply_text(
                f"🤔 **Decision:** {decision}\n\n"
                "Task kept as in-progress. Use `/retry`, `/complete`, or `/next`"
            )
            return False

        elif seems_complete or (not REQUIRE_APPROVAL and not has_errors and used_tools):
            # Seems complete or made progress without errors
            await bot_state.task_client.mark_complete(task.id)
            await update.message.reply_text(
                f"✅ **Task {task.id} marked as complete!**"
            )
            return True

        elif not REQUIRE_APPROVAL:
            # Auto-continue enabled, no errors, ask AI if it's done
            await update.message.reply_text("🔍 **Checking if task is complete...**")

            check_prompt = f"""Task: {task.title}
Description: {task.description[:300]}

Agent's work result:
{response.content[:800]}

Is this task complete? Reply with ONLY:
- "COMPLETE" if the task is fully done
- "INCOMPLETE: <reason>" if more work is needed"""

            check = await bot_state.agent.run(check_prompt, continue_session=False)
            check_result = check.content.strip().upper()

            if "COMPLETE" in check_result and "INCOMPLETE" not in check_result:
                await bot_state.task_client.mark_complete(task.id)
                await update.message.reply_text(
                    f"✅ **Task {task.id} marked as complete!**\n"
                    f"AI verification: {check.content[:200]}"
                )
                return True
            else:
                await update.message.reply_text(
                    f"⏸️ **Task needs more work**\n"
                    f"AI says: {check.content[:300]}\n\n"
                    "Use `/retry` to continue or `/next` to skip"
                )
                return False
        else:
            # REQUIRE_APPROVAL is true - ask user
            await update.message.reply_text(
                f"🤔 **Is task {task.id} complete?**\n"
                "Reply with:\n"
                "- `/complete` to mark as done\n"
                "- `/retry` to try again\n"
                "- `/next` to skip to next task"
            )
            return False

    except Exception as e:
        logger.error(f"Error working on task {task.id}: {e}")
        await update.message.reply_text(
            f"❌ **Error working on task {task.id}:**\n{str(e)[:500]}"
        )
        return False


async def autonomous_loop(update: Update, depth: int = 0):
    """
    Main autonomous loop - works through tasks automatically.

    Args:
        update: Telegram update object
        depth: Recursion depth to prevent infinite loops
    """
    if depth > 20:
        await update.message.reply_text(
            "⚠️ Maximum task depth reached (20). Stopping autonomous mode."
        )
        return

    if bot_state.paused:
        logger.info("Autonomous loop paused by user")
        await update.message.reply_text("⏸️ Autonomous mode paused")
        return

    # Get next task
    next_task = await bot_state.task_client.get_next_task()

    if not next_task:
        await update.message.reply_text(
            "🎉 **All tasks complete!** No more tasks available."
        )
        return

    # Store current task
    bot_state.current_task = next_task

    # Work on the task
    completed = await work_on_task(next_task, update)

    # If auto-continue is enabled and task completed, get next task
    if bot_state.auto_continue and completed and not bot_state.paused:
        await update.message.reply_text(
            "🔄 **Auto-continuing to next task...**"
        )
        # Recursive call
        await autonomous_loop(update, depth + 1)
    elif not completed:
        await update.message.reply_text(
            "⏸️ **Pausing for user input**\n"
            "Use `/next` to continue to next task"
        )


# Command handlers
@require_auth
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initialize the bot."""
    await update.message.reply_text(
        "🤖 **Autonomous Task-Master Bot**\n\n"
        f"**Model:** {bot_state.agent.model}\n"
        f"**Working Directory:** {WORKING_DIRECTORY}\n"
        f"**Auto-continue:** {'Enabled' if bot_state.auto_continue else 'Disabled'}\n\n"
        "**Commands:**\n"
        "/start - Show this message\n"
        "/auto - Start autonomous mode\n"
        "/next - Work on next task manually\n"
        "/pause - Pause autonomous mode\n"
        "/resume - Resume autonomous mode\n"
        "/status - Show current status\n"
        "/tasks - List all pending tasks\n"
        "/complete - Mark current task as complete\n"
        "/retry - Retry current task\n"
        "/models - Switch AI model\n"
        "/project <path> - Change working directory\n"
        "/clear - Clear agent session\n\n"
        "💡 **Tip:** Use `/auto` to start working through tasks automatically!"
    )


@require_auth
async def cmd_auto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start autonomous mode."""
    bot_state.paused = False
    await update.message.reply_text(
        "🚀 **Starting autonomous mode...**\n"
        "I'll work through tasks automatically.\n"
        "Use `/pause` to stop at any time."
    )
    await autonomous_loop(update)


@require_auth
async def cmd_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually trigger next task."""
    await autonomous_loop(update)


@require_auth
async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pause autonomous mode."""
    bot_state.paused = True
    await update.message.reply_text(
        "⏸️ **Autonomous mode paused**\n"
        "Use `/resume` to continue"
    )


@require_auth
async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resume autonomous mode."""
    bot_state.paused = False
    await update.message.reply_text("▶️ **Resuming autonomous mode...**")
    await autonomous_loop(update)


@require_auth
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current status."""
    status_msg = f"📊 **Bot Status**\n\n"
    status_msg += f"**Model:** {bot_state.agent.model}\n"
    status_msg += f"**Working Directory:** {bot_state.agent.working_dir}\n"
    status_msg += f"**Auto-continue:** {'Enabled' if bot_state.auto_continue else 'Disabled'}\n"
    status_msg += f"**Paused:** {'Yes' if bot_state.paused else 'No'}\n\n"

    if bot_state.current_task:
        status_msg += f"**Current Task:**\n"
        status_msg += f"ID: {bot_state.current_task.id}\n"
        status_msg += f"Title: {bot_state.current_task.title}\n"
        status_msg += f"Status: {bot_state.current_task.status}\n"
    else:
        status_msg += "**Current Task:** None\n"

    await update.message.reply_text(status_msg)


@require_auth
async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all tasks with clean, chat-friendly formatting."""
    await update.message.reply_text("📋 **Loading all tasks...**")

    # Get all tasks
    all_tasks = await bot_state.task_client.list_tasks()

    if not all_tasks:
        await update.message.reply_text("✅ **No tasks found!** Initialize with task-master.")
        return

    # Group tasks by status
    done_tasks = [t for t in all_tasks if t.status == "done"]
    in_progress_tasks = [t for t in all_tasks if t.status == "in-progress"]
    pending_tasks = [t for t in all_tasks if t.status == "pending"]

    # Build summary
    total = len(all_tasks)
    summary = f"📊 **Task Summary:** {len(done_tasks)}/{total} done, {len(in_progress_tasks)} in progress, {len(pending_tasks)} pending\n\n"

    # Show in-progress tasks
    if in_progress_tasks:
        summary += "🔄 **In Progress:**\n"
        for task in in_progress_tasks[:5]:  # Limit to 5 to avoid spam
            summary += f"  • {task.id} - {task.title[:50]}\n"
        if len(in_progress_tasks) > 5:
            summary += f"  ... and {len(in_progress_tasks) - 5} more\n"
        summary += "\n"

    # Show pending tasks
    if pending_tasks:
        summary += "⏳ **Pending:**\n"
        for task in pending_tasks[:8]:  # Show more pending tasks
            priority_icon = "🔴" if task.priority and "high" in task.priority.lower() else "🟡" if task.priority and "medium" in task.priority.lower() else ""
            summary += f"  {priority_icon} {task.id} - {task.title[:50]}\n"
        if len(pending_tasks) > 8:
            summary += f"  ... and {len(pending_tasks) - 8} more\n"
        summary += "\n"

    # Show recently completed (last 3)
    if done_tasks:
        summary += f"✅ **Completed:** {len(done_tasks)} tasks done\n"
        for task in done_tasks[-3:]:  # Last 3 completed
            summary += f"  • {task.id} - {task.title[:50]}\n"
        summary += "\n"

    # Get and highlight next task
    next_task = await bot_state.task_client.get_next_task()
    if next_task:
        summary += f"🎯 **Next Recommended:** {next_task.id} - {next_task.title}\n"
        summary += f"\n💡 Use `/auto` to start working automatically!"
    else:
        summary += "🎉 **All tasks complete!**"

    await update.message.reply_text(summary)


@require_auth
async def cmd_complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mark current task as complete."""
    if not bot_state.current_task:
        await update.message.reply_text("❌ No current task")
        return

    await bot_state.task_client.mark_complete(bot_state.current_task.id)
    await update.message.reply_text(
        f"✅ Task {bot_state.current_task.id} marked as complete!"
    )

    if bot_state.auto_continue:
        await update.message.reply_text("🔄 Moving to next task...")
        await autonomous_loop(update)


@require_auth
async def cmd_retry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retry current task."""
    if not bot_state.current_task:
        await update.message.reply_text("❌ No current task to retry")
        return

    await update.message.reply_text(
        f"🔄 Retrying task {bot_state.current_task.id}..."
    )
    await work_on_task(bot_state.current_task, update)


@require_auth
async def cmd_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Change working directory."""
    if not context.args:
        await update.message.reply_text(
            f"**Current working directory:** {bot_state.agent.working_dir}\n\n"
            "Usage: `/project <path>`"
        )
        return

    new_dir = " ".join(context.args)

    # Validate directory exists
    if not os.path.exists(new_dir):
        await update.message.reply_text(f"❌ Directory not found: {new_dir}")
        return

    bot_state.agent.set_working_directory(new_dir)
    bot_state.task_client.set_working_directory(new_dir)

    await update.message.reply_text(
        f"✅ **Working directory changed to:**\n`{new_dir}`"
    )


@require_auth
async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear agent session."""
    await bot_state.agent.clear_session()
    bot_state.current_task = None
    await update.message.reply_text("🗑️ Agent session cleared")


@require_auth
async def cmd_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch between available models."""
    # Available models
    models = {
        "1": ("xai/grok-code-fast-1", "Grok Code Fast 1 - Optimized for coding tasks"),
        "2": ("xai/grok-4-fast-non-reasoning", "Grok 4 Fast (Non-Reasoning) - Faster responses"),
        "3": ("xai/grok-4-fast-reasoning", "Grok 4 Fast (Reasoning) - Advanced reasoning"),
    }

    # If no argument, show current model and options
    if not context.args:
        current_model = bot_state.agent.model
        model_list = "🤖 **Model Selection**\n\n"
        model_list += f"**Current Model:** {current_model}\n\n"
        model_list += "**Available Models:**\n"
        for key, (model_id, description) in models.items():
            marker = "✅" if model_id == current_model else "  "
            model_list += f"{marker} **{key}.** {description}\n"
        model_list += f"\n💡 Reply with `/models <number>` to switch (e.g., `/models 1`)"
        await update.message.reply_text(model_list)
        return

    # Switch model
    choice = context.args[0]
    if choice not in models:
        await update.message.reply_text(
            f"❌ Invalid choice. Please select 1, 2, or 3.\n"
            f"Use `/models` to see available options."
        )
        return

    new_model_id, description = models[choice]

    # Update agent model
    bot_state.agent.model = new_model_id

    # Clear session when switching models
    await bot_state.agent.clear_session()

    await update.message.reply_text(
        f"✅ **Model switched!**\n\n"
        f"**New Model:** {description}\n"
        f"**ID:** {new_model_id}\n\n"
        f"Agent session cleared for clean start."
    )
    logger.info(f"Model switched to: {new_model_id}")


@require_auth
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle direct messages to the agent."""
    message_text = update.message.text
    logger.info(f"Direct message: {message_text[:100]}")

    await update.message.reply_text("🤖 Processing...")

    # Create event callback
    async def send_event(event):
        """Send parsed event to Telegram."""
        if event.type in ['tool', 'file', 'error', 'step']:
            try:
                await update.message.reply_text(event.message)
            except Exception as e:
                logger.error(f"Failed to send event: {e}")

    response = await bot_state.agent.run(
        message_text,
        continue_session=True,
        event_callback=send_event
    )

    # Send final response if meaningful
    if response.content and len(response.content) > 20:
        await update.message.reply_text(
            f"**Agent:**\n{response.content[:4000]}"
        )


def main():
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in .env")

    logger.info(f"Starting Autonomous Task-Master Bot (OpenCode)")
    logger.info(f"Model: {OPENCODE_MODEL}")
    logger.info(f"Working Directory: {WORKING_DIRECTORY}")

    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("auto", cmd_auto))
    application.add_handler(CommandHandler("next", cmd_next))
    application.add_handler(CommandHandler("pause", cmd_pause))
    application.add_handler(CommandHandler("resume", cmd_resume))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("tasks", cmd_tasks))
    application.add_handler(CommandHandler("complete", cmd_complete))
    application.add_handler(CommandHandler("retry", cmd_retry))
    application.add_handler(CommandHandler("models", cmd_models))
    application.add_handler(CommandHandler("project", cmd_project))
    application.add_handler(CommandHandler("clear", cmd_clear))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start bot
    logger.info("Bot started. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
