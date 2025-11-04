#!/usr/bin/env python3
"""
Quick diagnostic script to test configuration
"""

import os
from dotenv import load_dotenv

print("🔍 Testing Telegram CLI Bridge Configuration...\n")

# Load environment variables
load_dotenv()

# Check required variables
print("1. Checking environment variables...")
token = os.getenv("TELEGRAM_BOT_TOKEN")
user_id = os.getenv("ALLOWED_USER_ID")
cli_cmd = os.getenv("CLI_COMMAND")

if token and token != "your_telegram_bot_token_here":
    print("   ✅ TELEGRAM_BOT_TOKEN is set")
    print(f"      → {token[:10]}...{token[-10:]}")
else:
    print("   ❌ TELEGRAM_BOT_TOKEN not configured")
    print("      → Edit .env and add your token from @BotFather")

if user_id and user_id != "your_telegram_user_id_here":
    print(f"   ✅ ALLOWED_USER_ID is set: {user_id}")
else:
    print("   ❌ ALLOWED_USER_ID not configured")
    print("      → Edit .env and add your user ID from @userinfobot")

print(f"   ℹ️  CLI_COMMAND: {cli_cmd}")

# Check CLI command availability
print("\n2. Checking CLI command availability...")
import shutil
if shutil.which(cli_cmd):
    print(f"   ✅ '{cli_cmd}' command found in PATH")
else:
    print(f"   ⚠️  '{cli_cmd}' not found in PATH")
    print(f"      → Make sure '{cli_cmd}' is installed and accessible")

# Check dependencies
print("\n3. Checking Python dependencies...")
try:
    import telegram
    print("   ✅ python-telegram-bot installed")
except ImportError:
    print("   ❌ python-telegram-bot not installed")

try:
    import pexpect
    print("   ✅ pexpect installed")
except ImportError:
    print("   ❌ pexpect not installed")

# Summary
print("\n" + "="*50)
if token and user_id and token != "your_telegram_bot_token_here" and user_id != "your_telegram_user_id_here":
    print("✅ Configuration looks good!")
    print("\nNext steps:")
    print("1. Run: tg-bridge")
    print("2. Open Telegram and message your bot")
    print("3. Send /start to begin")
else:
    print("⚠️  Configuration incomplete")
    print("\nPlease edit .env file:")
    print(f"  nano {os.path.join(os.path.dirname(__file__), '.env')}")
    print("\nThen run this script again to verify.")
