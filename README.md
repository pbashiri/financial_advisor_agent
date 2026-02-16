# Financial Advisor Bot

A personal financial advisor Telegram chatbot powered by Claude. Provides investment-focused Q&A and daily market briefings personalized to your portfolio.

## Features

- **Conversational financial advisor** — ask about investments, portfolio strategy, market analysis
- **Daily market briefings** — automated morning briefings with indices, holdings P/L, watchlist, and AI sentiment summary
- **Conversation memory** — maintains context across messages (SQLite-backed, 50-message sliding window)
- **Portfolio-aware** — responses personalized to your holdings, risk tolerance, and goals
- **Authorization** — restricted to your Telegram user ID only

## Quick Start

### 1. Install uv (if not installed)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Clone and install dependencies

```bash
cd financial_advisor_agent_2
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

### 5. Run the bot

```bash
uv run python -m financial_advisor.main
```

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | List available commands |
| `/briefing` | Get today's market briefing |
| `/clear` | Clear conversation history |
| `/status` | Bot status and model info |
| `/profile` | View your loaded financial profile |

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
