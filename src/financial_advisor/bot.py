"""Telegram bot: command handlers, authorization, briefing scheduler."""

import json
import logging
from datetime import time as dt_time
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .agent import FinancialAdvisorAgent
from .briefing import generate_briefing
from .config import Settings
from .memory import ConversationMemory

logger = logging.getLogger(__name__)

TELEGRAM_MSG_LIMIT = 4096
PACIFIC = ZoneInfo("America/Los_Angeles")


def _is_authorized(user_id: int, settings: Settings) -> bool:
    return user_id in settings.allowed_user_ids


async def _send_long_message(
    update: Update, text: str, parse_mode: str | None = ParseMode.MARKDOWN
) -> None:
    """Send a message, splitting if it exceeds Telegram's 4096-char limit.
    Falls back to plain text if Markdown parsing fails."""
    chunks = _split_message(text, TELEGRAM_MSG_LIMIT)
    for chunk in chunks:
        try:
            await update.message.reply_text(chunk, parse_mode=parse_mode)
        except BadRequest as e:
            if "parse" in str(e).lower() or "can't" in str(e).lower():
                logger.warning("Markdown parse error, retrying without parse_mode: %s", e)
                await update.message.reply_text(chunk, parse_mode=None)
            else:
                raise


def _split_message(text: str, limit: int) -> list[str]:
    """Split text into chunks that fit within Telegram's message limit."""
    if len(text) <= limit:
        return [text]

    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        # Try to split at a newline near the limit
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1 or split_at < limit // 2:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


# --- Command Handlers ---


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    if not _is_authorized(update.effective_user.id, settings):
        await update.message.reply_text("Sorry, you are not authorized to use this bot.")
        return

    await update.message.reply_text(
        "Welcome to your *Personal Financial Advisor Agent*! \n\n"
        "I can help you with:\n"
        "- Investment analysis and portfolio questions\n"
        "- Market insights and stock research\n"
        "- Investment recommendations\n\n"
        "Commands:\n"
        "/help — Show available commands\n"
        "/briefing — Get today's market briefing\n"
        "/clear — Clear conversation history\n"
        "/status — Check bot status\n"
        "/profile — View your loaded profile\n\n"
        "Just send me any financial question to get started!",
        parse_mode=ParseMode.MARKDOWN,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    if not _is_authorized(update.effective_user.id, settings):
        return

    await update.message.reply_text(
        "*Available Commands*\n\n"
        "/start — Welcome message\n"
        "/help — This help message\n"
        "/briefing — Today's market briefing (indices, holdings, watchlist)\n"
        "/clear — Clear conversation history\n"
        "/status — Bot status and model info\n"
        "/profile — View your loaded financial profile\n\n"
        "Or just type any financial question!",
        parse_mode=ParseMode.MARKDOWN,
    )


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    if not _is_authorized(update.effective_user.id, settings):
        return

    memory: ConversationMemory = context.bot_data["memory"]
    deleted = await memory.clear_history(update.effective_user.id)
    await update.message.reply_text(
        f"Conversation cleared ({deleted} messages removed). Start fresh!"
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    if not _is_authorized(update.effective_user.id, settings):
        return

    has_profile = bool(settings.user_profile)
    briefing_time = f"{settings.briefing_hour:02d}:{settings.briefing_minute:02d} Pacific"

    await update.message.reply_text(
        f"*Bot Status*\n\n"
        f"Model: `{settings.claude_model}`\n"
        f"Profile loaded: {'Yes' if has_profile else 'No'}\n"
        f"Daily briefing: {briefing_time}\n"
        f"Your user ID: `{update.effective_user.id}`",
        parse_mode=ParseMode.MARKDOWN,
    )


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    if not _is_authorized(update.effective_user.id, settings):
        return

    if not settings.user_profile:
        await update.message.reply_text(
            "No profile loaded. Create `config/user_profile.json` based on "
            "`config/user_profile.example.json` and restart the bot."
        )
        return

    profile_str = json.dumps(settings.user_profile, indent=2)
    await _send_long_message(
        update,
        f"*Your Financial Profile*\n\n```json\n{profile_str}\n```",
    )


async def briefing_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    if not _is_authorized(update.effective_user.id, settings):
        return

    agent: FinancialAdvisorAgent = context.bot_data["agent"]
    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        text = await generate_briefing(settings, agent)
        await _send_long_message(update, text)
    except Exception:
        logger.exception("Briefing generation failed")
        await update.message.reply_text("Sorry, I couldn't generate the briefing right now.")


# --- Catch-all text handler ---


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    user_id = update.effective_user.id

    if not _is_authorized(user_id, settings):
        await update.message.reply_text("Sorry, you are not authorized to use this bot.")
        return

    agent: FinancialAdvisorAgent = context.bot_data["agent"]
    user_text = update.message.text

    # Show typing indicator
    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        response = await agent.chat(user_id, user_text)
        await _send_long_message(update, response)
    except Exception:
        logger.exception("Error handling message from user %s", user_id)
        await update.message.reply_text(
            "Sorry, I encountered an error processing your message. Please try again."
        )


# --- Scheduled briefing job ---


async def scheduled_briefing(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job callback: send daily briefing to all allowed users."""
    settings: Settings = context.bot_data["settings"]
    agent: FinancialAdvisorAgent = context.bot_data["agent"]

    logger.info("Running scheduled daily briefing")
    try:
        text = await generate_briefing(settings, agent)
    except Exception:
        logger.exception("Scheduled briefing generation failed")
        return

    for user_id in settings.allowed_user_ids:
        try:
            # Split and send
            chunks = _split_message(text, TELEGRAM_MSG_LIMIT)
            for chunk in chunks:
                try:
                    await context.bot.send_message(
                        chat_id=user_id, text=chunk, parse_mode=ParseMode.MARKDOWN
                    )
                except BadRequest:
                    await context.bot.send_message(chat_id=user_id, text=chunk)
        except Exception:
            logger.exception("Failed to send briefing to user %s", user_id)


# --- Bot builder ---


def create_bot(
    settings: Settings, memory: ConversationMemory, agent: FinancialAdvisorAgent
) -> Application:
    """Create and configure the Telegram bot application."""
    app = Application.builder().token(settings.telegram_bot_token).build()

    # Store shared objects in bot_data
    app.bot_data["settings"] = settings
    app.bot_data["memory"] = memory
    app.bot_data["agent"] = agent

    # Register command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("briefing", briefing_command))
    app.add_handler(CommandHandler("profile", profile_command))

    # Catch-all for text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Schedule daily briefing
    briefing_time = dt_time(
        hour=settings.briefing_hour,
        minute=settings.briefing_minute,
        tzinfo=PACIFIC,
    )
    app.job_queue.run_daily(scheduled_briefing, time=briefing_time, name="daily_briefing")
    logger.info(
        "Daily briefing scheduled at %02d:%02d Pacific",
        settings.briefing_hour,
        settings.briefing_minute,
    )

    return app
