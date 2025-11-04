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

# Load environment from current directory first, then fallback to script directory
load_dotenv(override=True)

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID"))
OPENCODE_MODEL = os.getenv("OPENCODE_MODEL", "grok-4-non-reasoning")
# Use WORKING_DIRECTORY from env, or default to current directory where command was run
WORKING_DIRECTORY = os.getenv("WORKING_DIRECTORY") or os.getcwd()
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


async def work_on_task(task: Task, update: Update, extra_context: str = "") -> bool:
    """
    Work on a specific task using OpenCode agent.

    Args:
        task: The task to work on
        update: Telegram update object
        extra_context: Additional context/instructions from user

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

Be thorough and transparent about what you're doing. Use tools as needed."""

    # Add extra context if provided
    if extra_context:
        prompt += f"\n\n**Additional Context/Instructions:**\n{extra_context}"

    try:
        # Track streaming output
        current_message = None
        accumulated_text = ""
        last_update_time = 0

        # Create event callback to send updates to Telegram
        async def send_event(event):
            """Send parsed event to Telegram."""
            nonlocal current_message, accumulated_text, last_update_time

            try:
                # Send tool/file/error/step events immediately
                if event.type in ['tool', 'file', 'error', 'step']:
                    await update.message.reply_text(event.message)

                # Stream text content as it arrives
                elif event.type == 'text':
                    import time
                    part = event.data.get('part', {})
                    text = part.get('text', '')

                    if text:
                        accumulated_text += text
                        current_time = time.time()

                        # Update message every 2 seconds or when we have significant content
                        if (current_time - last_update_time > 2.0 or len(accumulated_text) > 500):
                            try:
                                # Prepare display text (show last 3900 chars to leave room for header)
                                display_text = f"💭 **Agent thinking:**\n{accumulated_text[-3900:]}"

                                if current_message:
                                    # Edit existing message
                                    await current_message.edit_text(display_text)
                                else:
                                    # Create new message
                                    current_message = await update.message.reply_text(display_text)
                                last_update_time = current_time
                            except Exception as e:
                                logger.debug(f"Failed to update streaming message: {e}")

            except Exception as e:
                logger.error(f"Failed to send event: {e}")

        # Run OpenCode agent with event streaming
        response = await bot_state.agent.run(
            prompt=prompt,
            continue_session=True,
            event_callback=send_event
        )

        # Send final accumulated text if we have a message to update
        if current_message and accumulated_text:
            try:
                # Split into chunks if too long (Telegram limit is 4096)
                full_text = f"💭 **Agent output:**\n{accumulated_text}"
                if len(full_text) <= 4096:
                    await current_message.edit_text(full_text)
                else:
                    # Update first message with truncated indicator
                    await current_message.edit_text(
                        f"💭 **Agent output:**\n{accumulated_text[:3900]}...\n\n(continues below)"
                    )
                    # Send continuation in chunks
                    remaining = accumulated_text[3900:]
                    while remaining:
                        chunk = remaining[:4000]
                        remaining = remaining[4000:]
                        await update.message.reply_text(chunk)
            except Exception as e:
                logger.error(f"Failed to send final text: {e}")

        # Only send final response if we didn't already show it via streaming
        elif response.content and len(response.content) > 20:
            # Split into chunks if needed
            full_text = f"🤖 **Agent:**\n{response.content}"
            if len(full_text) <= 4096:
                await update.message.reply_text(full_text)
            else:
                # Send in chunks
                await update.message.reply_text(f"🤖 **Agent:**\n{response.content[:3900]}...")
                remaining = response.content[3900:]
                while remaining:
                    chunk = remaining[:4000]
                    remaining = remaining[4000:]
                    await update.message.reply_text(chunk)

        # Check if task appears complete
        # Look for strong completion indicators
        completion_patterns = [
            "task completed", "task finished", "successfully completed",
            "successfully implemented", "all done", "implementation complete",
            "all tests pass", "fully implemented", "task is complete"
        ]

        content_lower = response.content.lower()
        seems_complete = any(pattern in content_lower for pattern in completion_patterns)

        # Check for actual error indicators (not just the word "error" which could be in normal text)
        # Look for patterns that indicate real problems
        error_patterns = [
            "error:", "failed to", "failed:", "blocked by", "cannot complete",
            "unable to complete", "need help", "couldn't", "didn't work",
            "critical error", "exception:", "traceback", "fatal"
        ]

        has_errors = any(pattern in content_lower for pattern in error_patterns)

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

The response indicates errors or issues. Analyze the situation:

CONTINUE - If the agent is making progress and just needs more iterations to complete the task
BLOCKED - If there's a critical error that requires human intervention
COMPLETE - If the errors were handled and the task is actually done

Respond with just one word: CONTINUE, BLOCKED, or COMPLETE"""

            analysis = await bot_state.agent.run(analysis_prompt, continue_session=False)
            decision = analysis.content.strip().upper()

            if "CONTINUE" in decision:
                await update.message.reply_text(
                    f"🔄 **Continuing work on task {task.id}**\n"
                    "Agent needs more iterations..."
                )
                # Return False but don't stop - the autonomous loop will retry
                return False
            elif "BLOCKED" in decision:
                await update.message.reply_text(
                    f"🚫 **Task {task.id} blocked**\n"
                    f"Reason: {analysis.content[:200]}\n\n"
                    "Moving to next task..."
                )
                await bot_state.task_client.set_status(task.id, "blocked")
                return True  # Move to next task
            else:  # COMPLETE
                await bot_state.task_client.mark_complete(task.id)
                await update.message.reply_text(
                    f"✅ **Task {task.id} marked as complete!**"
                )
                return True

        elif seems_complete:
            # Task appears complete
            await bot_state.task_client.mark_complete(task.id)
            await update.message.reply_text(
                f"✅ **Task {task.id} marked as complete!**"
            )
            return True

        elif not REQUIRE_APPROVAL and used_tools:
            # Auto-continue enabled, made progress with tools
            # If agent used tools successfully and no errors, likely completed the work

            # Check if response indicates continuation is needed
            continuation_indicators = [
                "next step", "then i'll", "i will", "let me continue",
                "still need to", "next i'll", "continuing with"
            ]

            needs_continuation = any(
                indicator in content_lower
                for indicator in continuation_indicators
            )

            if needs_continuation:
                # Agent explicitly said it needs to continue
                await update.message.reply_text(
                    f"🔄 **Agent plans to continue...**"
                )
                return False
            else:
                # Agent used tools, no errors, no indication of more work
                # Assume task is complete
                await bot_state.task_client.mark_complete(task.id)
                await update.message.reply_text(
                    f"✅ **Task {task.id} marked as complete!**\n"
                    "(Tools used successfully, no errors)"
                )
                return True
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


async def autonomous_loop(update: Update, depth: int = 0, retry_count: int = 0, extra_context: str = ""):
    """
    Main autonomous loop - works through tasks automatically.

    Args:
        update: Telegram update object
        depth: Recursion depth to prevent infinite loops
        retry_count: Number of retries on current task
        extra_context: Additional context/instructions from user
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

    # Get next task (or continue current task)
    if retry_count == 0:
        next_task = await bot_state.task_client.get_next_task()
    else:
        next_task = bot_state.current_task

    if not next_task:
        await update.message.reply_text(
            "🎉 **All tasks complete!** No more tasks available."
        )
        return

    # Store current task
    bot_state.current_task = next_task

    # Work on the task (only use extra_context on first attempt, not retries)
    task_context = extra_context if retry_count == 0 else ""
    completed = await work_on_task(next_task, update, task_context)

    # If auto-continue is enabled
    if bot_state.auto_continue and not bot_state.paused:
        if completed:
            # Task completed, move to next (don't pass context to next task)
            await update.message.reply_text(
                "🔄 **Auto-continuing to next task...**"
            )
            await autonomous_loop(update, depth + 1, retry_count=0, extra_context="")
        elif retry_count < 3:
            # Task not complete but no critical error - retry
            await update.message.reply_text(
                f"🔄 **Retrying task {next_task.id}** (attempt {retry_count + 2}/4)"
            )
            await autonomous_loop(update, depth, retry_count + 1, extra_context=extra_context)
        else:
            # Max retries reached
            await update.message.reply_text(
                f"⏸️ **Task {next_task.id} needs attention**\n"
                f"Tried {retry_count + 1} times.\n\n"
                "Use `/retry` to try again, `/complete` to mark done, or `/next` to skip"
            )
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
        "/auto [context] - Start autonomous mode\n"
        "/next [context] - Work on next task manually\n"
        "/pause - Pause autonomous mode\n"
        "/resume - Resume autonomous mode\n"
        "/status - Show current status\n"
        "/tasks - List all pending tasks\n"
        "/sync - Verify task-master is in sync with code\n"
        "/complete - Mark current task as complete\n"
        "/retry [context] - Retry current task\n"
        "/models - Switch AI model\n"
        "/project <path> - Change working directory\n"
        "/clear - Clear agent session\n\n"
        "💡 **Tip:** Add extra context to commands:\n"
        "  `/auto focus on performance`\n"
        "  `/retry use simpler approach`"
    )


@require_auth
async def cmd_auto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start autonomous mode with optional extra context."""
    bot_state.paused = False

    # Extract extra context from message (anything after /auto command)
    extra_context = " ".join(context.args) if context.args else ""

    if extra_context:
        await update.message.reply_text(
            f"🚀 **Starting autonomous mode...**\n"
            f"I'll work through tasks automatically.\n"
            f"**Extra context:** {extra_context}\n\n"
            "Use `/pause` to stop at any time."
        )
    else:
        await update.message.reply_text(
            "🚀 **Starting autonomous mode...**\n"
            "I'll work through tasks automatically.\n"
            "Use `/pause` to stop at any time."
        )

    await autonomous_loop(update, extra_context=extra_context)


@require_auth
async def cmd_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually trigger next task with optional extra context."""
    # Extract extra context from message
    extra_context = " ".join(context.args) if context.args else ""

    if extra_context:
        await update.message.reply_text(f"📝 **Extra context:** {extra_context}")

    await autonomous_loop(update, extra_context=extra_context)


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
    """Retry current task with optional extra context."""
    if not bot_state.current_task:
        await update.message.reply_text("❌ No current task to retry")
        return

    # Extract extra context from message
    extra_context = " ".join(context.args) if context.args else ""

    if extra_context:
        await update.message.reply_text(
            f"🔄 Retrying task {bot_state.current_task.id}...\n"
            f"**Extra context:** {extra_context}"
        )
    else:
        await update.message.reply_text(
            f"🔄 Retrying task {bot_state.current_task.id}..."
        )

    await work_on_task(bot_state.current_task, update, extra_context)


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
async def cmd_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verify task-master is in sync with codebase and update if needed."""
    await update.message.reply_text(
        "🔍 **Analyzing codebase vs task-master status...**\n"
        "This will check if completed tasks are actually done and update accordingly."
    )

    try:
        # Get all tasks
        all_tasks = await bot_state.task_client.list_tasks()
        done_tasks = [t for t in all_tasks if t.status == "done"]
        in_progress_tasks = [t for t in all_tasks if t.status == "in-progress"]
        pending_tasks = [t for t in all_tasks if t.status == "pending"]

        # Create analysis prompt
        analysis_prompt = f"""I need you to analyze the codebase and verify if task-master tasks are in sync with reality.

**Current Task Status:**

**Done ({len(done_tasks)} tasks):**
{chr(10).join(f"- Task {t.id}: {t.title}" for t in done_tasks[:10])}
{"..." if len(done_tasks) > 10 else ""}

**In Progress ({len(in_progress_tasks)} tasks):**
{chr(10).join(f"- Task {t.id}: {t.title}" for t in in_progress_tasks)}

**Pending ({len(pending_tasks)} tasks):**
{chr(10).join(f"- Task {t.id}: {t.title}" for t in pending_tasks[:10])}
{"..." if len(pending_tasks) > 10 else ""}

**Your Task:**
1. Analyze the codebase to check what's actually implemented
2. For each "done" task, verify it's actually complete in the code
3. For "in-progress" tasks, check if they're actually done
4. For "pending" tasks, check if they're already implemented

**Report Format:**
For each discrepancy found:
- Task ID
- Current status
- Actual status based on code
- Brief reason (what you found/didn't find)

If everything is in sync, just say "✅ All tasks are in sync with codebase"

Be thorough but efficient. Focus on major features, not minor details."""

        # Run analysis using agent
        await update.message.reply_text("🤖 **Agent analyzing codebase...**")

        response = await bot_state.agent.run(
            prompt=analysis_prompt,
            continue_session=False
        )

        # Send analysis results
        result_text = f"📊 **Sync Analysis Results:**\n\n{response.content}"

        # Split if too long
        if len(result_text) <= 4096:
            await update.message.reply_text(result_text)
        else:
            await update.message.reply_text(result_text[:3900] + "...\n\n(continues below)")
            remaining = result_text[3900:]
            while remaining:
                chunk = remaining[:4000]
                remaining = remaining[4000:]
                await update.message.reply_text(chunk)

        # Check if updates are needed
        if "discrepancy" in response.content.lower() or "mismatch" in response.content.lower():
            await update.message.reply_text(
                "⚠️ **Discrepancies found!**\n\n"
                "Would you like me to update task-master?\n"
                "Reply with:\n"
                "- `/sync update` to automatically update tasks\n"
                "- Or manually run `task-master set-status --id=X --status=done`"
            )
        else:
            await update.message.reply_text("✅ **Everything looks good!**")

    except Exception as e:
        logger.error(f"Sync analysis error: {e}")
        await update.message.reply_text(
            f"❌ **Error during sync analysis:**\n{str(e)[:500]}"
        )


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
    application.add_handler(CommandHandler("sync", cmd_sync))
    application.add_handler(CommandHandler("models", cmd_models))
    application.add_handler(CommandHandler("project", cmd_project))
    application.add_handler(CommandHandler("clear", cmd_clear))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start bot
    logger.info("Bot started. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
