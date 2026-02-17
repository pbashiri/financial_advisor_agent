"""Entry point: load config, configure logging, start bot."""

import logging
import sys

from .agent import FinancialAdvisorAgent
from .api_client import ApiClient
from .bot import create_bot
from .config import load_settings
from .memory import ConversationMemory


def setup_logging(level: str) -> None:
    """Configure logging to console and file."""
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    try:
        from .config import PROJECT_ROOT

        log_dir = PROJECT_ROOT / "data"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "bot.log")
        handlers.append(file_handler)
    except Exception:
        pass  # File logging is optional

    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format=log_format,
        handlers=handlers,
    )

    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)


async def async_main() -> None:
    """Async initialization and bot startup."""
    settings = load_settings()
    setup_logging(settings.log_level)

    logger = logging.getLogger(__name__)
    logger.info("Starting Financial Advisor Bot")
    logger.info("Model: %s", settings.claude_model)
    logger.info("Allowed users: %s", settings.allowed_user_ids)

    # Initialize conversation memory
    memory = ConversationMemory(settings.db_path)
    await memory.initialize()

    # Create agent
    agent = FinancialAdvisorAgent(settings, memory)

    # Create API client (gracefully handles API being offline)
    api_client = ApiClient(settings.api_base_url)
    api_online = await api_client.health()
    if api_online:
        logger.info("API backend reachable at %s", settings.api_base_url)
    else:
        logger.warning(
            "API backend not reachable at %s — portfolio commands will use fallback",
            settings.api_base_url,
        )

    # Create and run bot
    app = create_bot(settings, memory, agent, api_client)

    logger.info("Bot is starting (polling mode)...")
    # run_polling handles its own event loop
    # We need to use the async approach since we're already in an async context
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Bot is running! Press Ctrl+C to stop.")

        # Keep running until interrupted
        import asyncio

        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            await app.updater.stop()
            await app.stop()
            await api_client.close()
            await memory.close()


def main() -> None:
    """Synchronous entry point."""
    import asyncio

    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nBot stopped.")


if __name__ == "__main__":
    main()
