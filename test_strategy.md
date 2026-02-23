# V2 Test Strategy: Hands-On Feature Assessment

## ✅ V2.4 Complete - All Features Wired Up & Bot Ready

All V2 features are fully integrated with the Telegram bot. You can now test everything directly via Telegram commands!

| Layer | Features | How to test |
|---|---|---|
| **V0-V1** (core) | Chat, briefing, portfolio, CSV import, inline keyboards | Telegram bot + API backend |
| **V2** (NEW) | `/recommend`, `/alerts`, `/news` commands + scheduled jobs | Telegram bot (requires V2 setup*) |

**V2 Setup Required:**
- FINNHUB_API_KEY in .env (free tier at finnhub.io)
- Ollama running with `nomic-embed-text` model
- ChromaDB (auto-configured on first run)

*Note: Bot will show helpful error messages if V2 dependencies aren't configured.*

---

## Part 1: Setup

### Prerequisites

```bash
cd /Users/Pedram/Workspace/financial_advisor_agent/financial_advisor_agent
git checkout v2
uv sync --all-extras
```

### 1. Verify config

Your `.env` should already be configured. Verify:

```bash
uv run python -c "from src.financial_advisor.config import load_settings; s = load_settings(); print(f'Config OK - model: {s.claude_model}')"
```

### 2. Run unit tests (baseline)

```bash
uv run python -m pytest -v
```

All 100 tests should pass before manual testing.

### 3. Start the FastAPI backend (needed for portfolio features)

```bash
uv run uvicorn financial_advisor.api.app:create_app --factory --port 8000 &
```

### 4. Start the Telegram bot

```bash
uv run python -m financial_advisor.main
```

### 5. (Optional) For V2 backend features — start Ollama

```bash
ollama pull nomic-embed-text
ollama serve  # if not already running
```

---

## Part 2: Test Wired-Up Features (via Telegram)

Open your bot in Telegram and work through these.

### A. Core Chat

| Test | What to do | What to look for |
|---|---|---|
| Basic Q&A | Ask "What's a good asset allocation for someone in their 30s?" | Personalized response referencing your profile, disclaimer at bottom |
| Portfolio-aware | Ask "How is my portfolio doing?" | Should reference your actual holdings |
| Follow-up context | Ask a follow-up like "What about adding more bonds?" | Should remember the previous message |
| Edge case | Send just "hi" | Should respond naturally, not crash |

### B. Commands

| Command | What to verify |
|---|---|
| `/start` | Welcome message with inline keyboard menu |
| `/help` | Lists all available commands |
| `/status` | Shows model name, profile loaded, API health, your user ID |
| `/profile` | Dumps your user_profile.json contents |
| `/briefing` | Full market briefing — indices, holdings P/L, watchlist movers, AI summary |
| `/portfolio` | Live portfolio table with current prices, gain/loss per holding |
| `/clear` | Confirms history cleared; next message should have no prior context |

### C. CSV Import

The bot accepts `.csv` file uploads in Telegram to import portfolio holdings.

**Required columns:** `symbol`, `shares`, `cost_basis`
**Optional columns:** `account_type` (brokerage, roth_ira, traditional_ira, 401k, hsa, other), `notes`

**Step 1: Create a test CSV file**

Save one of these as a `.csv` file on your device:

Minimal (required columns only):
```csv
symbol,shares,cost_basis
NVDA,10,450.00
AMZN,5,175.00
GOOGL,15,140.00
```

Full (all columns):
```csv
symbol,shares,cost_basis,account_type,notes
NVDA,10,450.00,brokerage,AI play
AMZN,5,175.00,roth_ira,Core holding
GOOGL,15,140.00,brokerage,Added on dip
VTI,50,220.00,401k,Total market index
SCHD,100,75.00,brokerage,Dividend ETF
```

**Step 2: Send to bot**

Open Telegram, tap the attachment/paperclip icon, select the `.csv` file, and send it to the bot.

**Step 3: Verify**

| What to check | Expected result |
|---|---|
| Bot response | "Imported X holdings" with count |
| `/portfolio` | New holdings appear with live prices and P/L |
| Duplicate symbols | Should update existing holdings, not create duplicates |

**Edge cases to test:**

Bad header — should get an error about missing columns:
```csv
ticker,quantity,price
AAPL,10,150.00
```

Bad data — should report row-level errors and skip bad rows:
```csv
symbol,shares,cost_basis
AAPL,ten,150.00
,5,200.00
MSFT,20,invalid
GOOGL,15,140.00
```

Empty file — send an empty `.csv`, bot should handle gracefully.

Non-CSV file — send a `.txt` or `.pdf`, bot should reject it with a format hint.

**Via curl (alternative — requires API backend running):**

```bash
# Import from a file
curl -X POST http://localhost:8000/portfolio/import \
  -F "file=@test_holdings.csv"

# Import from raw text
curl -X POST http://localhost:8000/portfolio/import/text \
  -H "Content-Type: application/json" \
  -d '{"content": "symbol,shares,cost_basis\nNVDA,10,450.00\nAMZN,5,175.00"}'
```

### D. Inline Keyboards

After `/start`, tap the menu buttons. Verify they trigger the right actions (briefing, portfolio, etc.).

---

## Part 3: Test the FastAPI Backend (via curl)

While the backend is running on port 8000:

```bash
# Health check
curl http://localhost:8000/health

# Get portfolio
curl http://localhost:8000/portfolio

# Get a stock quote
curl http://localhost:8000/market/quote/AAPL

# Get major indices
curl http://localhost:8000/market/indices

# Portfolio analytics
curl http://localhost:8000/analytics/summary | python -m json.tool

# Allocation breakdown
curl http://localhost:8000/analytics/allocation | python -m json.tool

# Add a holding via API
curl -X POST http://localhost:8000/portfolio \
  -H "Content-Type: application/json" \
  -d '{"symbol": "GOOGL", "shares": 10, "cost_basis": 140.00}'

# Then verify in Telegram with /portfolio
```

---

## Part 4: Test V2 Bot Commands (via Telegram)

**Prerequisites for V2 features:**
- FINNHUB_API_KEY in .env
- Ollama running with nomic-embed-text model
- ChromaDB configured (automatic on first run)

If these aren't configured, V2 commands will show helpful error messages.

### A. `/recommend SYMBOL` Command

Test AI-powered stock recommendations:

```
You: /recommend AAPL
Bot: [Generates full recommendation with BUY/SELL/HOLD, confidence, reasoning, risks]
```

**What to verify:**
- Bot shows typing indicator
- Recommendation includes action (BUY/SELL/HOLD)
- Includes confidence level (HIGH/MEDIUM/LOW)
- Contains reasoning and risk factors
- References news articles if available
- Considers portfolio context

**Edge cases:**
- Invalid ticker: `/recommend XYZFAKE123`
- During market hours vs after hours
- Stock with no recent news
- Stock already in portfolio vs new stock

### B. `/alerts` Command

Test alert management:

```
You: /alerts
Bot: [Shows alert command help]

You: /alerts create AAPL price_above 200
Bot: ✅ Alert created (ID: 1)
     AAPL price_above $200.00

You: /alerts list
Bot: *Configured Alerts*
     ✅ ID 1: price_above — AAPL price_above $200.00

You: /alerts recent
Bot: No alerts triggered in the last 24 hours.
```

**What to verify:**
- Alert creation returns ID
- List shows all configured alerts
- Recent shows triggered alerts with timestamps
- Delete removes alerts
- Alert notifications arrive when conditions met (wait for scheduled job)

**Edge cases:**
- Create alert with invalid threshold: `/alerts create AAPL price_above notanumber`
- Delete non-existent alert: `/alerts delete 999`
- Create multiple alerts for same symbol
- Alert triggers during scheduled check (wait 30 min)

### C. `/news QUERY` Command

Test RAG-powered news search:

```
You: /news Apple earnings
Bot: *News Search Results for:* Apple earnings

     1. *Apple Reports Q4 Earnings Beat* (Reuters)
        Apple Inc reported better-than-expected...
        [Read more](url) | Relevance: 0.87
     ...
```

**What to verify:**
- Returns relevant articles (top 5)
- Shows headline, source, summary
- Includes clickable URL
- Relevance score displayed
- Handles queries with no results

**Edge cases:**
- Very broad query: `/news stocks`
- Very specific query: `/news Apple M4 chip launch date`
- Query with no matches (before news ingestion runs)
- Special characters in query

### D. Scheduled Jobs

**Alert Checking (every 30 minutes):**
1. Create a price alert with current price threshold
2. Wait 30 minutes
3. Verify alert check runs (check logs)
4. If alert triggers, verify Telegram notification
5. Verify 24h dedup (alert shouldn't re-trigger immediately)

**News Ingestion (every 4 hours):**
1. Check logs for "Running scheduled news ingestion"
2. Verify articles are fetched for holdings + watchlist
3. After ingestion, `/news` should return results
4. Verify ChromaDB database grows (check data/chromadb/)

**Logs to monitor:**
```bash
tail -f data/bot.log | grep -E "(Alert|News|Recommendation)"
```

## Part 5: Test V2 Backend Features Directly (Python REPL)

If you want to test V2 components without Telegram:

### A. News / RAG Pipeline

Requires `FINNHUB_API_KEY` in `.env`.

```bash
uv run python -c "
import asyncio
from financial_advisor.news.finnhub_client import FinnhubClient

async def test():
    client = FinnhubClient('YOUR_FINNHUB_KEY')
    articles = await client.fetch_news('AAPL')
    print(f'Fetched {len(articles)} articles')
    for a in articles[:3]:
        print(f'  - {a.headline} ({a.source})')
    await client.close()

asyncio.run(test())
"
```

### B. Embedder + Vector Store

Requires Ollama running with `nomic-embed-text`.

```bash
uv run python -c "
import asyncio
from financial_advisor.news.embedder import OllamaEmbedder

async def test():
    embedder = OllamaEmbedder()
    vec = await embedder.embed('Apple stock earnings report')
    print(f'Embedding dim: {len(vec)}, first 5: {vec[:5]}')

asyncio.run(test())
"
```

### C. Alert Engine

```bash
uv run python -c "
import asyncio
from financial_advisor.alerts.storage import AlertStorage
from financial_advisor.alerts.engine import AlertEngine
from financial_advisor.alerts.models import AlertConfig, AlertType

async def test():
    storage = AlertStorage('data/test_alerts.db')
    await storage.initialize()

    # Create a price alert
    config = AlertConfig(alert_type=AlertType.PRICE_ABOVE, symbol='AAPL', threshold=100.0)
    config_id = await storage.save_config(config)
    print(f'Created alert config: id={config_id}')

    # Run check cycle
    engine = AlertEngine(storage)
    triggered = await engine.run_check_cycle()
    print(f'Triggered alerts: {len(triggered)}')
    for a in triggered:
        print(f'  {a.message}')

    await storage.close()

asyncio.run(test())
"
```

### D. Recommendation Workflow

This makes real Claude Sonnet API calls (~$0.02-0.05 per run).

```bash
uv run python -c "
import asyncio
from anthropic import AsyncAnthropic
from financial_advisor.portfolio.storage import PortfolioStorage
from financial_advisor.workflows.recommendations import RecommendationEngine

async def test():
    client = AsyncAnthropic()  # reads ANTHROPIC_API_KEY from env
    storage = PortfolioStorage('data/portfolio.db')
    await storage.initialize()

    engine = RecommendationEngine(
        anthropic_client=client,
        analysis_model='claude-sonnet-4-5-20250929',
        portfolio_storage=storage,
    )

    result = await engine.generate('AAPL', user_id=97566988)
    print(result.get('recommendation_text', 'No output'))

asyncio.run(test())
"
```

---

## Part 6: Comprehensive Testing Checklist

### Core Reliability (V0-V1)

- [ ] All `/commands` respond without errors
- [ ] Bot recovers gracefully if the API backend is down
- [ ] `/briefing` works on weekends (no market data)
- [ ] Bot handles rapid-fire messages without crashing
- [ ] Claude responses are personalized to your profile
- [ ] Briefing prices are accurate (spot-check a few)
- [ ] Conversation memory works across multiple messages
- [ ] Portfolio P/L calculations look correct

### V2 Features

**Recommendations:**
- [ ] `/recommend AAPL` generates full recommendation
- [ ] Includes BUY/SELL/HOLD action and confidence level
- [ ] Contains reasoning and risk factors
- [ ] Handles invalid tickers gracefully
- [ ] Works without news (if vector store empty)

**Alerts:**
- [ ] `/alerts create` creates price alerts successfully
- [ ] `/alerts list` shows all configured alerts
- [ ] `/alerts delete` removes alerts
- [ ] Alert checking runs every 30 minutes (check logs)
- [ ] Telegram notifications sent when alerts trigger
- [ ] 24h dedup prevents alert spam

**News/RAG:**
- [ ] `/news` returns relevant articles
- [ ] Search results include headlines, sources, URLs
- [ ] Handles queries with no results gracefully
- [ ] News ingestion runs every 4 hours (check logs)
- [ ] Articles stored in ChromaDB (check data/chromadb/)

### V2 Graceful Degradation

- [ ] Bot starts without FINNHUB_API_KEY (V2 disabled)
- [ ] Bot starts without Ollama running (V2 disabled)
- [ ] `/recommend` shows helpful error if disabled
- [ ] `/alerts` shows helpful error if disabled
- [ ] `/news` shows helpful error if disabled
- [ ] `/help` only shows available commands
- [ ] `/start` only mentions available features

### Edge Cases (V0-V2)

- [ ] Invalid ticker: "How is XYZFAKE123 doing?"
- [ ] Very long message (500+ characters)
- [ ] Rapid-fire messages (5+ in quick succession)
- [ ] `/portfolio` with API backend stopped
- [ ] `/briefing` outside market hours
- [ ] `/recommend` with invalid symbol
- [ ] `/alerts create` with non-numeric threshold
- [ ] `/news` with empty query

### Scheduled Jobs

- [ ] Alert check runs at configured interval
- [ ] News ingestion runs at configured interval
- [ ] Jobs handle errors gracefully (logged, not fatal)
- [ ] Daily briefing still sends at scheduled time

---

## ✅ Feature Wiring Status (V2.4 COMPLETE)

| Feature | Backend | Bot Integration | Scheduled Job | Status |
|---|---|---|---|---|
| Alerts | ✅ Done | ✅ `/alerts` command | ✅ Every 30min | **COMPLETE** |
| News/RAG | ✅ Done | ✅ `/news` command | ✅ Every 4hr | **COMPLETE** |
| Recommendations | ✅ Done | ✅ `/recommend` command | N/A | **COMPLETE** |
| Human-in-the-loop | ✅ State ready | Pending user input | N/A | Future |

## V2.4 Implementation Summary

**Commit:** `5869b59` - feat: V2.4 — wire up alerts, news/RAG, and recommendations to bot

**Files Changed:**
- `main.py` - Initialize V2 engines with graceful degradation
- `bot.py` - Add command handlers and scheduled job callbacks
- `api_client.py` - Add `get_portfolio_holdings()` method
- `README.md` - Document V2 features and setup

**Tests:** 100/100 passing ✅

**What's New:**
1. Three new bot commands: `/recommend`, `/alerts`, `/news`
2. Two scheduled jobs: alert checking, news ingestion
3. Graceful degradation: bot runs without V2 if deps unavailable
4. Dynamic feature detection: `/help` shows only available commands
