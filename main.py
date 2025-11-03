#!/usr/bin/env python3
"""
Telegram CLI Bridge Bot

A bot that enables remote interaction with a CLI tool from Telegram.
Relays CLI prompts to Telegram and forwards user responses back to the CLI.
"""

import os
import sys
import logging
import re
from typing import Optional
from functools import wraps

import pexpect
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
PROMPT_REGEX = os.getenv("PROMPT_REGEX", r".*[>?]$")
CLI_TIMEOUT = int(os.getenv("CLI_TIMEOUT", "30"))

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

# Global CLI process variable
cli_process: Optional[pexpect.spawn] = None


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


@require_auth
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command - launch the CLI process."""
    global cli_process

    if cli_process is not None and cli_process.isalive():
        await update.message.reply_text("CLI process is already running.")
        return

    try:
        # Spawn the CLI process
        logger.info(f"Starting CLI process: {CLI_COMMAND}")
        cli_process = pexpect.spawn(CLI_COMMAND, timeout=CLI_TIMEOUT)

        await update.message.reply_text(f"CLI process started: {CLI_COMMAND}")

        # Try to capture initial output
        try:
            cli_process.expect(PROMPT_REGEX, timeout=5)
            output = cli_process.before.decode("utf-8", errors="ignore").strip()
            if output:
                await send_chunked_message(update, output)
        except pexpect.TIMEOUT:
            logger.info("No initial output from CLI")
        except pexpect.EOF:
            await update.message.reply_text("CLI process terminated unexpectedly.")
            cli_process = None

    except Exception as e:
        logger.error(f"Failed to start CLI: {e}")
        await update.message.reply_text(f"Failed to start CLI: {str(e)}")
        cli_process = None


@require_auth
async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stop command - terminate the CLI process."""
    global cli_process

    if cli_process is None or not cli_process.isalive():
        await update.message.reply_text("No CLI process is currently running.")
        return

    try:
        # Try graceful termination first
        cli_process.terminate()
        cli_process.wait(timeout=5)
        logger.info("CLI process terminated gracefully")
    except pexpect.TIMEOUT:
        # Force kill if termination fails
        logger.warning("CLI process did not terminate gracefully, forcing kill")
        cli_process.kill(9)
    finally:
        cli_process = None
        await update.message.reply_text("CLI process stopped.")


@require_auth
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages - relay input to CLI and capture output."""
    global cli_process

    if cli_process is None or not cli_process.isalive():
        await update.message.reply_text("No CLI process is running. Use /start to begin.")
        return

    user_input = update.message.text

    try:
        # Send input to CLI
        cli_process.sendline(user_input)
        logger.info(f"Sent to CLI: {user_input}")

        # Capture output
        try:
            cli_process.expect(PROMPT_REGEX, timeout=CLI_TIMEOUT)
            output = cli_process.before.decode("utf-8", errors="ignore").strip()

            if output:
                await send_chunked_message(update, output)
            else:
                logger.info("No output from CLI")

        except pexpect.TIMEOUT:
            await update.message.reply_text(
                "CLI operation timed out. The process may still be running. "
                "Use /stop to terminate it."
            )
        except pexpect.EOF:
            await update.message.reply_text("CLI process terminated.")
            cli_process = None

    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await update.message.reply_text(f"Error: {str(e)}")


async def send_chunked_message(update: Update, text: str) -> None:
    """Send large text in chunks to avoid Telegram message size limits."""
    MAX_MESSAGE_LENGTH = 4096

    if len(text) <= MAX_MESSAGE_LENGTH:
        await update.message.reply_text(text)
    else:
        # Split into chunks
        for i in range(0, len(text), MAX_MESSAGE_LENGTH):
            chunk = text[i:i + MAX_MESSAGE_LENGTH]
            await update.message.reply_text(chunk)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors in the application."""
    logger.error(f"Update {update} caused error: {context.error}")


def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Register error handler
    application.add_error_handler(error_handler)

    logger.info("Bot started. Press Ctrl+C to stop.")

    # Start polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
