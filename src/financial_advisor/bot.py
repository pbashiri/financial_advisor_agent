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
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .agent import FinancialAdvisorAgent
from .api_client import ApiClient
from .briefing import generate_briefing
from .config import Settings
from .keyboards import main_menu_keyboard, portfolio_keyboard
from .memory import ConversationMemory

logger = logging.getLogger(__name__)

TELEGRAM_MSG_LIMIT = 4096
PACIFIC = ZoneInfo("America/Los_Angeles")
MAX_CSV_SIZE_BYTES = 1_000_000  # 1 MB


def _is_authorized(user_id: int, settings: Settings) -> bool:
    return user_id in settings.allowed_user_ids


async def _send_long_message(
    update: Update, text: str, parse_mode: str | None = ParseMode.MARKDOWN, reply_markup=None
) -> None:
    """Send a message, splitting if it exceeds Telegram's 4096-char limit.
    Falls back to plain text if Markdown parsing fails."""
    chunks = _split_message(text, TELEGRAM_MSG_LIMIT)
    for i, chunk in enumerate(chunks):
        # Only attach reply_markup to the last chunk
        markup = reply_markup if i == len(chunks) - 1 else None
        try:
            await update.message.reply_text(chunk, parse_mode=parse_mode, reply_markup=markup)
        except BadRequest as e:
            if "parse" in str(e).lower() or "can't" in str(e).lower():
                logger.warning("Markdown parse error, retrying without parse_mode: %s", e)
                await update.message.reply_text(chunk, parse_mode=None, reply_markup=markup)
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
        "/portfolio — Live portfolio summary\n"
        "/briefing — Get today's market briefing\n"
        "/clear — Clear conversation history\n"
        "/status — Check bot status\n"
        "/profile — View your loaded profile\n\n"
        "Just send me any financial question to get started!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    if not _is_authorized(update.effective_user.id, settings):
        return

    await update.message.reply_text(
        "*Available Commands*\n\n"
        "/start — Welcome message\n"
        "/help — This help message\n"
        "/portfolio — Live portfolio summary with P/L\n"
        "/briefing — Today's market briefing (indices, holdings, watchlist)\n"
        "/clear — Clear conversation history\n"
        "/status — Bot status and model info\n"
        "/profile — View your loaded financial profile\n\n"
        "*Import Holdings*\n"
        "Send a CSV file with columns: symbol, shares, cost\\_basis, account\\_type, notes\n\n"
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

    # Check if API is reachable
    api_client: ApiClient = context.bot_data["api_client"]
    api_status = "✅ Online" if await api_client.health() else "⚠️ Offline (bot uses fallback)"

    await update.message.reply_text(
        f"*Bot Status*\n\n"
        f"Model: `{settings.claude_model}`\n"
        f"Profile loaded: {'Yes' if has_profile else 'No'}\n"
        f"Daily briefing: {briefing_time}\n"
        f"API backend: {api_status}\n"
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


async def portfolio_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show live portfolio summary via the FastAPI backend."""
    settings: Settings = context.bot_data["settings"]
    if not _is_authorized(update.effective_user.id, settings):
        return

    await update.message.chat.send_action(ChatAction.TYPING)

    api_client: ApiClient = context.bot_data["api_client"]
    text = await api_client.get_portfolio_summary_text()

    if text:
        await _send_long_message(update, text, reply_markup=portfolio_keyboard())
    else:
        # Fallback: use briefing-style holdings from user_profile
        from .briefing import _format_holdings_section

        fallback_text = await _format_holdings_section(settings)
        if fallback_text:
            await _send_long_message(
                update,
                "*Portfolio (live prices)*\n\n" + fallback_text,
                reply_markup=portfolio_keyboard(),
            )
        else:
            await update.message.reply_text(
                "Portfolio data unavailable. Make sure the API server is running "
                "or check your holdings in /profile.",
                reply_markup=main_menu_keyboard(),
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


# --- CSV document upload handler ---


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle CSV file uploads for importing holdings."""
    settings: Settings = context.bot_data["settings"]
    if not _is_authorized(update.effective_user.id, settings):
        return

    document = update.message.document
    if not document:
        return

    filename = document.file_name or ""
    if not filename.lower().endswith(".csv"):
        await update.message.reply_text(
            "Please send a CSV file to import holdings.\n\n"
            "Format: `symbol,shares,cost_basis,account_type,notes`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await update.message.chat.send_action(ChatAction.TYPING)

    # Download file
    try:
        file = await context.bot.get_file(document.file_id)
        content_bytes = await file.download_as_bytearray()
        if len(content_bytes) > MAX_CSV_SIZE_BYTES:
            await update.message.reply_text(
                "CSV file is too large. Please upload a file smaller than 1 MB."
            )
            return
        csv_text = content_bytes.decode("utf-8")
    except Exception:
        logger.exception("Failed to download CSV file")
        await update.message.reply_text("Failed to download the file. Please try again.")
        return

    api_client: ApiClient = context.bot_data["api_client"]
    result = await api_client.import_csv_text(csv_text)

    if result is None:
        await update.message.reply_text(
            "The API server is not running. Start it with:\n"
            "`uvicorn financial_advisor.api.app:app --port 8000`\n\n"
            "Or use Docker Compose: `docker compose up`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    imported = result.get("imported", 0)
    skipped = result.get("skipped", 0)
    errors = result.get("errors", [])

    msg = f"✅ Imported *{imported}* holdings"
    if skipped:
        msg += f", skipped *{skipped}* rows"
    if errors:
        error_text = "\n".join(f"• {e}" for e in errors[:5])
        msg += f"\n\n⚠️ Errors:\n{error_text}"
        if len(errors) > 5:
            msg += f"\n...and {len(errors) - 5} more"

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


# --- Inline keyboard callback handler ---


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard button presses."""
    query = update.callback_query
    await query.answer()

    settings: Settings = context.bot_data["settings"]
    if not _is_authorized(query.from_user.id, settings):
        return

    data = query.data

    if data == "portfolio":
        api_client: ApiClient = context.bot_data["api_client"]
        text = await api_client.get_portfolio_summary_text()
        if text:
            await query.message.reply_text(
                text, parse_mode=ParseMode.MARKDOWN, reply_markup=portfolio_keyboard()
            )
        else:
            await query.message.reply_text(
                "Portfolio data unavailable. Make sure the API server is running.",
                reply_markup=main_menu_keyboard(),
            )

    elif data == "briefing":
        agent: FinancialAdvisorAgent = context.bot_data["agent"]
        try:
            text = await generate_briefing(settings, agent)
            chunks = _split_message(text, TELEGRAM_MSG_LIMIT)
            for chunk in chunks:
                try:
                    await query.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
                except BadRequest:
                    await query.message.reply_text(chunk)
        except Exception:
            logger.exception("Briefing generation failed from callback")
            await query.message.reply_text("Briefing generation failed.")

    elif data == "analysis":
        api_client: ApiClient = context.bot_data["api_client"]
        text = await api_client.get_portfolio_summary_text()
        if text:
            await query.message.reply_text(
                text, parse_mode=ParseMode.MARKDOWN, reply_markup=portfolio_keyboard()
            )
        else:
            await query.message.reply_text(
                "Analysis unavailable. Make sure the API server is running.",
                reply_markup=main_menu_keyboard(),
            )

    elif data in ("help", "menu"):
        await query.message.reply_text(
            "*Available Commands*\n\n"
            "/portfolio — Live portfolio summary\n"
            "/briefing — Today's market briefing\n"
            "/help — Full command list\n\n"
            "Or type any financial question!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(),
        )


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
    settings: Settings,
    memory: ConversationMemory,
    agent: FinancialAdvisorAgent,
    api_client: ApiClient,
) -> Application:
    """Create and configure the Telegram bot application."""
    app = Application.builder().token(settings.telegram_bot_token).build()

    # Store shared objects in bot_data
    app.bot_data["settings"] = settings
    app.bot_data["memory"] = memory
    app.bot_data["agent"] = agent
    app.bot_data["api_client"] = api_client

    # Register command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("briefing", briefing_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("portfolio", portfolio_command))

    # Inline keyboard callbacks
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    # Document uploads (CSV import)
    app.add_handler(MessageHandler(filters.Document.FileExtension("csv"), handle_document))

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
