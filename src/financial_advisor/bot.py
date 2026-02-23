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

    # Check which V2 features are available
    has_recommendations = context.bot_data.get("recommendation_engine") is not None
    has_alerts = context.bot_data.get("alert_engine") is not None
    has_news = context.bot_data.get("news_pipeline") is not None

    v2_features = []
    if has_recommendations:
        v2_features.append("- AI-powered stock recommendations")
    if has_alerts:
        v2_features.append("- Price and portfolio alerts")
    if has_news:
        v2_features.append("- RAG-powered news search")

    v2_text = ""
    if v2_features:
        v2_text = "\n\n*V2 Features (NEW):*\n" + "\n".join(v2_features)

    await update.message.reply_text(
        "Welcome to your *Personal Financial Advisor Agent*! \n\n"
        "I can help you with:\n"
        "- Investment analysis and portfolio questions\n"
        "- Market insights and stock research\n"
        "- Daily market briefings\n"
        "- Portfolio tracking and analytics"
        f"{v2_text}\n\n"
        "*Core Commands:*\n"
        "/help — Show all commands\n"
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

    # Check which V2 features are available
    has_recommendations = context.bot_data.get("recommendation_engine") is not None
    has_alerts = context.bot_data.get("alert_engine") is not None
    has_news = context.bot_data.get("news_pipeline") is not None

    v2_commands = []
    if has_recommendations:
        v2_commands.append("/recommend SYMBOL — AI-powered stock recommendation")
    if has_alerts:
        v2_commands.append("/alerts — Manage price and portfolio alerts")
    if has_news:
        v2_commands.append("/news QUERY — Search news with RAG")

    v2_text = ""
    if v2_commands:
        v2_text = "\n\n*V2 Commands:*\n" + "\n".join(v2_commands)

    await update.message.reply_text(
        "*Available Commands*\n\n"
        "*Core:*\n"
        "/start — Welcome message\n"
        "/help — This help message\n"
        "/portfolio — Live portfolio summary with P/L\n"
        "/briefing — Today's market briefing (indices, holdings, watchlist)\n"
        "/clear — Clear conversation history\n"
        "/status — Bot status and model info\n"
        "/profile — View your loaded financial profile"
        f"{v2_text}\n\n"
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
        agent: FinancialAdvisorAgent = context.bot_data["agent"]
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


# --- V2 Command Handlers ---


async def recommend_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate AI-powered recommendation for a stock symbol."""
    settings: Settings = context.bot_data["settings"]
    if not _is_authorized(update.effective_user.id, settings):
        return

    recommendation_engine = context.bot_data.get("recommendation_engine")
    if not recommendation_engine:
        await update.message.reply_text(
            "❌ Recommendation engine not available.\n\n"
            "Requirements:\n"
            "- FINNHUB_API_KEY in .env\n"
            "- Ollama running with nomic-embed-text model\n"
            "- ChromaDB configured"
        )
        return

    # Parse symbol from command (e.g., /recommend AAPL)
    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: `/recommend SYMBOL`\n\n"
            "Example: `/recommend AAPL`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    symbol = args[0].upper()
    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        result = await recommendation_engine.generate(symbol, update.effective_user.id)

        # Format and send recommendation
        recommendation_text = result.get("recommendation_text", "No recommendation generated")
        await _send_long_message(update, recommendation_text)

    except Exception as e:
        logger.exception("Recommendation failed for %s", symbol)
        await update.message.reply_text(
            f"❌ Failed to generate recommendation for {symbol}.\n\n"
            f"Error: {str(e)}"
        )


async def alerts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manage price and portfolio alerts."""
    settings: Settings = context.bot_data["settings"]
    if not _is_authorized(update.effective_user.id, settings):
        return

    alert_engine = context.bot_data.get("alert_engine")
    if not alert_engine:
        await update.message.reply_text("❌ Alert engine not available")
        return

    # Parse subcommand (e.g., /alerts list, /alerts create AAPL price_above 200)
    args = context.args
    if not args:
        await update.message.reply_text(
            "*Alert Commands*\n\n"
            "`/alerts list` — Show all configured alerts\n"
            "`/alerts recent` — Show recently triggered alerts\n"
            "`/alerts create SYMBOL price_above THRESHOLD` — Create price alert\n"
            "`/alerts create SYMBOL price_below THRESHOLD` — Create price alert\n"
            "`/alerts delete ID` — Delete an alert\n\n"
            "Example: `/alerts create AAPL price_above 200`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    subcommand = args[0].lower()

    if subcommand == "list":
        from .alerts.storage import AlertStorage
        storage: AlertStorage = alert_engine._storage
        configs = await storage.get_configs(enabled_only=False)

        if not configs:
            await update.message.reply_text("No alerts configured.")
            return

        lines = ["*Configured Alerts*\n"]
        for cfg in configs:
            status = "✅" if cfg.enabled else "⏸"
            lines.append(
                f"{status} ID {cfg.id}: {cfg.alert_type.value} — {cfg.description}"
            )

        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    elif subcommand == "recent":
        recent = await alert_engine.get_recent_triggered(hours=24)

        if not recent:
            await update.message.reply_text("No alerts triggered in the last 24 hours.")
            return

        lines = ["*Recently Triggered Alerts*\n"]
        for alert in recent:
            ack = "✓" if alert.acknowledged else "!"
            lines.append(f"{ack} {alert.message} (at {alert.triggered_at})")

        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    elif subcommand == "create":
        # Expected: /alerts create AAPL price_above 200
        if len(args) < 4:
            await update.message.reply_text(
                "Usage: `/alerts create SYMBOL price_above|price_below THRESHOLD`\n\n"
                "Example: `/alerts create AAPL price_above 200`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        symbol = args[1].upper()
        alert_type_str = args[2].lower()

        try:
            threshold = float(args[3])
        except ValueError:
            await update.message.reply_text("❌ Invalid threshold (must be a number)")
            return

        from .alerts.models import AlertConfig, AlertType

        if alert_type_str == "price_above":
            alert_type = AlertType.PRICE_ABOVE
        elif alert_type_str == "price_below":
            alert_type = AlertType.PRICE_BELOW
        else:
            await update.message.reply_text(
                f"❌ Unknown alert type: {alert_type_str}\n\n"
                "Supported: price_above, price_below"
            )
            return

        config = AlertConfig(
            alert_type=alert_type,
            symbol=symbol,
            threshold=threshold,
            description=f"{symbol} {alert_type_str} ${threshold:.2f}",
        )

        from .alerts.storage import AlertStorage
        storage: AlertStorage = alert_engine._storage
        config_id = await storage.save_config(config)

        await update.message.reply_text(
            f"✅ Alert created (ID: {config_id})\n\n"
            f"{config.description}"
        )

    elif subcommand == "delete":
        if len(args) < 2:
            await update.message.reply_text("Usage: `/alerts delete ID`", parse_mode=ParseMode.MARKDOWN)
            return

        try:
            alert_id = int(args[1])
        except ValueError:
            await update.message.reply_text("❌ Invalid alert ID (must be a number)")
            return

        from .alerts.storage import AlertStorage
        storage: AlertStorage = alert_engine._storage
        success = await storage.delete_config(alert_id)

        if success:
            await update.message.reply_text(f"✅ Alert {alert_id} deleted")
        else:
            await update.message.reply_text(f"❌ Alert {alert_id} not found")

    else:
        await update.message.reply_text(
            f"❌ Unknown subcommand: {subcommand}\n\n"
            "Try: list, recent, create, delete"
        )


async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Search news using RAG (semantic search over embedded articles)."""
    settings: Settings = context.bot_data["settings"]
    if not _is_authorized(update.effective_user.id, settings):
        return

    news_pipeline = context.bot_data.get("news_pipeline")
    if not news_pipeline:
        await update.message.reply_text(
            "❌ News/RAG pipeline not available.\n\n"
            "Requirements:\n"
            "- FINNHUB_API_KEY in .env\n"
            "- Ollama running with nomic-embed-text model\n"
            "- ChromaDB configured"
        )
        return

    # Parse query (e.g., /news AI chip stocks)
    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: `/news QUERY`\n\n"
            "Example: `/news Apple earnings report`\n\n"
            "This searches embedded news articles using semantic similarity.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    query = " ".join(args)
    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        embedder = news_pipeline._embedder
        vector_store = news_pipeline._vector_store

        # Embed query and search
        query_embedding = await embedder.embed(query)
        results = vector_store.search(query_embedding, top_k=5)

        if not results:
            await update.message.reply_text(
                f"No news articles found for: *{query}*\n\n"
                "Try running news ingestion first or wait for the scheduled ingestion job.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        # Format results
        lines = [f"*News Search Results for:* {query}\n"]
        for i, (article, score) in enumerate(results, 1):
            lines.append(
                f"{i}. *{article.headline}* ({article.source})\n"
                f"   {article.summary[:150]}...\n"
                f"   [Read more]({article.url}) | Relevance: {score:.2f}\n"
            )

        await _send_long_message(update, "\n".join(lines))

    except Exception as e:
        logger.exception("News search failed for query: %s", query)
        await update.message.reply_text(
            f"❌ News search failed.\n\n"
            f"Error: {str(e)}"
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


async def scheduled_alert_check(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job callback: check all alert conditions and notify users of triggered alerts."""
    settings: Settings = context.bot_data["settings"]
    alert_engine = context.bot_data.get("alert_engine")

    if not alert_engine:
        return

    logger.info("Running scheduled alert check")
    try:
        # Fetch current portfolio holdings for drift alerts
        api_client: ApiClient = context.bot_data["api_client"]
        holdings = None
        try:
            holdings_data = await api_client.get_portfolio_holdings()
            if holdings_data:
                from .portfolio.models import Holding
                holdings = [Holding(**h) for h in holdings_data]
        except Exception:
            logger.warning("Could not fetch holdings for alert check")

        # Run alert check cycle
        triggered_alerts = await alert_engine.run_check_cycle(holdings=holdings)

        # Send notifications to all allowed users
        if triggered_alerts:
            for user_id in settings.allowed_user_ids:
                try:
                    lines = ["🔔 *Alert Triggered*\n"]
                    for alert in triggered_alerts:
                        lines.append(f"• {alert.message}")

                    message = "\n".join(lines)
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=message,
                        parse_mode=ParseMode.MARKDOWN,
                    )
                except Exception:
                    logger.exception("Failed to send alert to user %s", user_id)

    except Exception:
        logger.exception("Alert check cycle failed")


async def scheduled_news_ingestion(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job callback: fetch and embed news for portfolio symbols."""
    settings: Settings = context.bot_data["settings"]
    news_pipeline = context.bot_data.get("news_pipeline")

    if not news_pipeline:
        return

    logger.info("Running scheduled news ingestion")
    try:
        # Get symbols from user profile holdings and watchlist
        symbols = set()

        holdings = settings.user_profile.get("holdings", [])
        for holding in holdings:
            if "symbol" in holding:
                symbols.add(holding["symbol"].upper())

        watchlist = settings.user_profile.get("watchlist", [])
        symbols.update(s.upper() for s in watchlist)

        if not symbols:
            logger.info("No symbols to ingest (no holdings or watchlist)")
            return

        # Run ingestion
        stats = await news_pipeline.ingest_for_symbols(list(symbols), days_back=3)

        logger.info(
            "News ingestion complete: %d symbols, %d fetched, %d new, %d stored",
            stats.symbols_processed,
            stats.articles_fetched,
            stats.articles_new,
            stats.articles_stored,
        )

        # Also ingest general market news
        general_stats = await news_pipeline.ingest_general_news()
        logger.info(
            "General news ingestion: %d fetched, %d new, %d stored",
            general_stats.articles_fetched,
            general_stats.articles_new,
            general_stats.articles_stored,
        )

    except Exception:
        logger.exception("News ingestion failed")


# --- Bot builder ---


def create_bot(
    settings: Settings,
    memory: ConversationMemory,
    agent: FinancialAdvisorAgent,
    api_client: ApiClient,
    alert_engine=None,
    news_pipeline=None,
    recommendation_engine=None,
) -> Application:
    """Create and configure the Telegram bot application."""
    app = Application.builder().token(settings.telegram_bot_token).build()

    # Store shared objects in bot_data
    app.bot_data["settings"] = settings
    app.bot_data["memory"] = memory
    app.bot_data["agent"] = agent
    app.bot_data["api_client"] = api_client
    app.bot_data["alert_engine"] = alert_engine
    app.bot_data["news_pipeline"] = news_pipeline
    app.bot_data["recommendation_engine"] = recommendation_engine

    # Register command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("briefing", briefing_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("portfolio", portfolio_command))

    # V2 command handlers (may be disabled if dependencies not available)
    app.add_handler(CommandHandler("recommend", recommend_command))
    app.add_handler(CommandHandler("alerts", alerts_command))
    app.add_handler(CommandHandler("news", news_command))

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

    # V2: Schedule alert checking (if alert engine is available)
    if alert_engine:
        app.job_queue.run_repeating(
            scheduled_alert_check,
            interval=settings.alert_check_interval_minutes * 60,
            first=10,  # Start 10 seconds after bot launch
            name="alert_check",
        )
        logger.info(
            "Alert checking scheduled every %d minutes",
            settings.alert_check_interval_minutes,
        )

    # V2: Schedule news ingestion (if news pipeline is available)
    if news_pipeline:
        app.job_queue.run_repeating(
            scheduled_news_ingestion,
            interval=settings.news_fetch_interval_hours * 3600,
            first=60,  # Start 60 seconds after bot launch
            name="news_ingestion",
        )
        logger.info(
            "News ingestion scheduled every %d hours",
            settings.news_fetch_interval_hours,
        )

    return app
