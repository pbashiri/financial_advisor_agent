# Financial Advisor Bot

A personal financial advisor Telegram chatbot powered by Claude. Provides investment-focused Q&A and daily market briefings personalized to your portfolio.

## Features

### Core (V0-V1)
- **Conversational financial advisor** — ask about investments, portfolio strategy, market analysis
- **Daily market briefings** — automated morning briefings with indices, holdings P/L, watchlist, and AI sentiment summary
- **Portfolio analytics** — live portfolio tracking with P/L, allocation breakdown, and performance metrics
- **CSV import** — bulk import holdings via CSV file upload
- **FastAPI backend** — RESTful API for portfolio management and market data
- **Conversation memory** — maintains context across messages (SQLite-backed, 50-message sliding window)
- **Authorization** — restricted to your Telegram user ID only

### V2 Features (NEW)
- **AI-powered recommendations** — LangGraph workflow with Claude Sonnet analysis for BUY/SELL/HOLD decisions
- **Smart alerts** — price alerts and portfolio drift notifications with scheduled checking
- **RAG-powered news** — semantic search over embedded financial news articles (Finnhub + Ollama + ChromaDB)
- **Scheduled jobs** — automated alert checking and news ingestion

## Quick Start

### 1. Install uv (if not installed)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Clone and install dependencies

```bash
cd financial_advisor_agent
uv sync --all-extras
```

This auto-downloads Python 3.12 and installs all dependencies.

### 3. Set up credentials

```bash
cp .env.example .env
```

Edit `.env` with your keys:

- **Telegram bot token**: Message `@BotFather` on Telegram → `/newbot` → copy token
- **Your Telegram user ID**: Message `@userinfobot` on Telegram → copy your numeric ID
- **Anthropic API key**: https://console.anthropic.com → API Keys → Create Key

### 4. Set up your financial profile

```bash
cp config/user_profile.example.json config/user_profile.json
```

Edit `config/user_profile.json` with your actual holdings, watchlist, risk tolerance, and goals.

### 5. (Optional) Set up V2 features

V2 features require additional dependencies:

**For Recommendations and News:**
- Get a free Finnhub API key at https://finnhub.io
- Install and start Ollama with the embedding model:
  ```bash
  ollama pull nomic-embed-text
  ollama serve
  ```

Add to your `.env`:
```bash
FINNHUB_API_KEY=your_finnhub_key_here
OLLAMA_BASE_URL=http://localhost:11434  # default
CHROMADB_PATH=data/chromadb  # default
CLAUDE_MODEL_ANALYSIS=claude-sonnet-4-5-20250929  # for recommendations
ALERT_CHECK_INTERVAL_MINUTES=30  # default
NEWS_FETCH_INTERVAL_HOURS=4  # default
```

**Note:** If these are not configured, the bot will run without V2 features (recommendations, alerts, news will be disabled).

### 6. Run the bot

```bash
uv run python -m financial_advisor.main
```

### 7. (Optional) Run the FastAPI backend

For portfolio features via the API:
```bash
uv run uvicorn financial_advisor.api.app:create_app --factory --port 8000
```

## Bot Commands

### Core Commands
| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | List available commands |
| `/portfolio` | Live portfolio summary with P/L |
| `/briefing` | Get today's market briefing |
| `/clear` | Clear conversation history |
| `/status` | Bot status and model info |
| `/profile` | View your loaded financial profile |

### V2 Commands (Optional - requires additional setup)
| Command | Description |
|---------|-------------|
| `/recommend SYMBOL` | Get AI-powered stock recommendation |
| `/alerts` | Manage price and portfolio alerts |
| `/alerts list` | Show all configured alerts |
| `/alerts create SYMBOL price_above PRICE` | Create price alert |
| `/alerts delete ID` | Delete an alert |
| `/news QUERY` | Search financial news with semantic search |

Or just type any financial question!

## Project Structure

```
src/financial_advisor/
├── main.py         # Entry point
├── config.py       # Settings from .env + user_profile.json
├── bot.py          # Telegram handlers and briefing scheduler
├── agent.py        # Claude API wrapper with conversation memory
├── memory.py       # Async SQLite conversation storage
├── briefing.py     # Daily briefing generation
├── market_data.py  # yfinance wrapper for quotes
└── prompts.py      # System prompt and disclaimers
```

## Running Tests

```bash
uv run pytest -v
```

## Cost

Uses Claude Haiku 4.5 by default (~$5/month for typical personal use of 50-100 queries/day). Requires separate Anthropic API billing (not included in Claude Max subscription).
