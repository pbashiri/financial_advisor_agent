"""Entry point: load config, configure logging, start bot."""

import logging
import sys

from anthropic import AsyncAnthropic

from .agent import FinancialAdvisorAgent
from .alerts.engine import AlertEngine
from .alerts.storage import AlertStorage
from .api_client import ApiClient
from .bot import create_bot
from .config import load_settings
from .memory import ConversationMemory
from .news.embedder import OllamaEmbedder
from .news.finnhub_client import FinnhubClient
from .news.ingestion import NewsIngestionPipeline
from .news.vector_store import NewsVectorStore
from .portfolio.storage import PortfolioStorage
from .workflows.recommendations import RecommendationEngine


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
    logging.getLogger("chromadb").setLevel(logging.WARNING)


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

    # V2: Initialize alert engine
    alert_storage = AlertStorage(settings.db_path.parent / "alerts.db")
    await alert_storage.initialize()
    alert_engine = AlertEngine(alert_storage)
    logger.info("Alert engine initialized")

    # V2: Initialize news/RAG pipeline (optional - requires Finnhub + Ollama)
    news_pipeline = None
    recommendation_engine = None
    if settings.finnhub_api_key:
        try:
            finnhub = FinnhubClient(settings.finnhub_api_key)
            embedder = OllamaEmbedder(base_url=settings.ollama_base_url)
            vector_store = NewsVectorStore(settings.chromadb_path)
            news_pipeline = NewsIngestionPipeline(finnhub, embedder, vector_store)
            logger.info("News/RAG pipeline initialized")

            # V2: Initialize recommendation engine (requires news pipeline + Anthropic)
            anthropic_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
            portfolio_storage = PortfolioStorage(settings.db_path.parent / "portfolio.db")
            await portfolio_storage.initialize()
            recommendation_engine = RecommendationEngine(
                anthropic_client=anthropic_client,
                analysis_model=settings.claude_model_analysis,
                portfolio_storage=portfolio_storage,
                vector_store=vector_store,
                embedder=embedder,
            )
            logger.info("Recommendation engine initialized (model: %s)", settings.claude_model_analysis)
        except Exception as e:
            logger.warning("Could not initialize news/RAG pipeline: %s", e)
            logger.warning("News and recommendation features will be disabled")
    else:
        logger.info("FINNHUB_API_KEY not set — news and recommendation features disabled")

    # Create and run bot
    app = create_bot(
        settings,
        memory,
        agent,
        api_client,
        alert_engine=alert_engine,
        news_pipeline=news_pipeline,
        recommendation_engine=recommendation_engine,
    )

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
            await alert_storage.close()
            if news_pipeline:
                await news_pipeline._finnhub.close()


def main() -> None:
    """Synchronous entry point."""
    import asyncio

    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nBot stopped.")


if __name__ == "__main__":
    main()
