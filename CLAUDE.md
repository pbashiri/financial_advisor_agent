# Claude Code Instructions - Financial Advisor Bot

## Living Project Doc (Read First)

**At the start of every session, read this doc to understand current status, priorities, and what's next:**

- **Google Doc:** https://docs.google.com/document/d/1lA2ll23JkX0ZsmGK1tT1EDvHqXy8kDx949ew76wwbEw
- **Access:** Via the `gdrive` MCP server (always available in Claude Code)
- **Contains:** Project vision, roadmap with live status, tech decisions, budget tracking, dev log

```
# How to read it at session start:
ReadMcpResourceTool(server="gdrive", uri="gdrive:///1lA2ll23JkX0ZsmGK1tT1EDvHqXy8kDx949ew76wwbEw")
```

---

## Project Overview

This is a personal Telegram chatbot that provides AI-powered financial advice using Claude. It's a **production bot** serving real users with real financial data.

**Critical:** This bot handles sensitive financial information and uses paid API services (Telegram, Anthropic Claude). Always exercise caution when making changes.

## Project Context

- **Type:** Production Telegram bot (single-user, personal use)
- **Language:** Python 3.12+
- **Package Manager:** uv (fast, modern Python package manager)
- **AI Model:** Claude Haiku 4.5 (cost-optimized for personal use)
- **Database:** SQLite (async via aiosqlite)
- **Deployment:** Manual/background process (not containerized)

## Core Principles

### 1. Safety First
- **NEVER commit .env files** - Contains production API keys and tokens
- **NEVER commit config/user_profile.json** - Contains personal financial data
- **ALWAYS run tests before pushing changes** - Bot serves real user
- **ALWAYS verify configuration loads** - Invalid config will crash the bot
- **BE CAUTIOUS with database changes** - Conversation history is valuable

### 2. Cost Awareness
- This bot uses **paid Anthropic API** (~$5/month on Haiku)
- Prefer Claude Haiku for routine tasks (cost-effective)
- Only suggest Sonnet/Opus upgrades if explicitly requested
- Be mindful of API call volume in tests and development

### 3. User Experience
- Bot serves a single user (Telegram ID: 97566988)
- Responses should be concise and actionable
- Financial disclaimers are automatically appended (see [prompts.py](src/financial_advisor/prompts.py))
- Conversation memory is limited to 50 messages (sliding window)

## Development Workflow

### Starting Development Session
```bash
cd /Users/Pedram/Workspace/financial_advisor_agent/financial_advisor_agent
uv sync --all-extras  # Ensure dependencies are current
```

### Making Code Changes
1. **Read existing code first** - Understand current implementation
2. **Run tests** - Ensure existing functionality works
3. **Make focused changes** - Keep modifications minimal and targeted
4. **Test changes** - Run relevant tests
5. **Verify bot still starts** - Check configuration loads correctly

### Testing Protocol

**Always run tests before committing:**
```bash
uv run python -m pytest -v
```

**All tests must pass (20/20):**
- Config tests (7) - Settings validation
- Market data tests (6) - yfinance integration
- Memory tests (7) - Database operations

**Test configuration loading:**
```bash
uv run python -c "from src.financial_advisor.config import load_settings; settings = load_settings(); print('✓ Config OK')"
```

### Running the Bot

**Start bot (foreground):**
```bash
uv run python -m financial_advisor.main
```

**Start bot (background):**
```bash
nohup uv run python -m financial_advisor.main > bot.log 2>&1 &
```

**Stop bot:**
```bash
ps aux | grep financial_advisor.main
kill <PID>
```

**Check logs:**
```bash
tail -f data/bot.log
```

## Project Structure

```
src/financial_advisor/
├── main.py         # Entry point - bot initialization and lifecycle
├── config.py       # Settings loader (reads .env + user_profile.json)
├── bot.py          # Telegram handlers, commands, scheduled briefing
├── agent.py        # Claude API wrapper with conversation memory
├── memory.py       # Async SQLite for conversation history
├── briefing.py     # Daily market briefing generation
├── market_data.py  # yfinance wrapper for stock quotes
└── prompts.py      # System prompts and financial disclaimers

tests/
├── test_config.py       # Configuration loading and validation
├── test_market_data.py  # Market data fetching
└── test_memory.py       # Database operations
```

## Configuration Files

### .env (NEVER commit)
Contains production secrets:
- `TELEGRAM_BOT_TOKEN` - From @BotFather
- `ANTHROPIC_API_KEY` - From console.anthropic.com
- `ALLOWED_TELEGRAM_USER_IDS` - Numeric Telegram user ID (97566988)
- `BRIEFING_HOUR`, `BRIEFING_MINUTE` - Daily briefing schedule (Pacific time)
- `CLAUDE_MODEL` - AI model to use (default: claude-haiku-4-5-20251001)
- `LOG_LEVEL` - Logging verbosity (default: INFO)

**If .env is missing or invalid, bot will crash on startup.**

### config/user_profile.json (NEVER commit)
Contains personal financial data:
- User name, risk tolerance, investment horizon
- Holdings (symbols, shares, cost basis)
- Watchlist (stocks to monitor)
- Investment goals and custom rules
- Account information

**This personalizes all bot responses and briefings.**

## Code Style & Conventions

### General Guidelines
- **Type hints:** Use where helpful, especially for public functions
- **Async/await:** Required for Telegram and database operations
- **Error handling:** Graceful degradation (e.g., missing stock quotes shouldn't crash bot)
- **Logging:** Use structured logging with appropriate levels (DEBUG, INFO, WARNING, ERROR)

### Formatting
- **Line length:** 100 characters (configured in pyproject.toml)
- **Linter:** Ruff (run with `uv run ruff check .`)
- **Formatter:** Ruff (run with `uv run ruff format .`)

### Testing
- **Framework:** pytest with pytest-asyncio
- **Async tests:** Use `async def test_*()` - asyncio mode is auto
- **Database tests:** Use temporary in-memory databases
- **No real API calls in tests** - Mock external services

## Common Tasks

### Adding a New Bot Command

1. **Add handler in [bot.py](src/financial_advisor/bot.py):**
```python
async def command_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /commandname"""
    # Implementation
```

2. **Register command in `setup_bot()`:**
```python
application.add_handler(CommandHandler("commandname", command_name_handler))
```

3. **Update `/help` command** to list new command

4. **Add tests** in `tests/test_bot.py` (if not exists, create it)

### Changing the AI Model

Edit `.env`:
```bash
# For better quality (higher cost):
CLAUDE_MODEL=claude-sonnet-4-5-20250929

# For best quality (highest cost):
CLAUDE_MODEL=claude-opus-4-6

# For cost optimization (lower quality):
CLAUDE_MODEL=claude-haiku-4-5-20251001
```

Restart the bot for changes to take effect.

### Modifying System Prompt

Edit [src/financial_advisor/prompts.py](src/financial_advisor/prompts.py):
- `DISCLAIMER` - Appended to all responses
- `build_system_prompt()` - Generates full system prompt with user context

**Test thoroughly** - prompt changes affect all AI responses.

### Updating Market Data Sources

Edit [src/financial_advisor/market_data.py](src/financial_advisor/market_data.py):
- Currently uses yfinance (free, no API key required)
- For alternatives, consider: Alpha Vantage, Polygon.io, IEX Cloud
- **Remember:** Most real-time market data APIs require paid subscriptions

### Adjusting Conversation Memory

Edit [src/financial_advisor/memory.py](src/financial_advisor/memory.py):
- Default: 50 messages per user (sliding window)
- Increase for longer context (higher token costs)
- Decrease for cost savings (less context)

## Deployment Considerations

### Production Checklist
- [ ] .env file configured with valid API keys
- [ ] config/user_profile.json exists and contains user data
- [ ] All tests passing (`uv run python -m pytest -v`)
- [ ] Bot starts without errors
- [ ] Daily briefing time is correct for user's timezone
- [ ] Log file location is writable
- [ ] Database directory exists and is writable

### Monitoring
- **Logs:** [data/bot.log](data/bot.log)
- **Database:** [data/conversations.db](data/conversations.db)
- **Process:** `ps aux | grep financial_advisor`

### Troubleshooting

**Bot not responding:**
1. Check bot is running: `ps aux | grep financial_advisor`
2. Check logs: `tail -f data/bot.log`
3. Verify Telegram user ID is in ALLOWED_TELEGRAM_USER_IDS
4. Test bot token with Telegram API

**Configuration errors:**
1. Verify .env file exists and is readable
2. Check ALLOWED_TELEGRAM_USER_IDS is numeric (not 'p765111')
3. Validate user_profile.json is valid JSON
4. Ensure all required env vars are set

**Market data failures:**
1. Check internet connection
2. yfinance sometimes has rate limits - wait and retry
3. Verify ticker symbols are valid (NYSE/NASDAQ)
4. Check for yfinance library updates

**Database errors:**
1. Check data/ directory exists and is writable
2. Verify SQLite database isn't corrupted
3. If corrupted, delete conversations.db (will lose history)

## Security Notes

### API Keys
- **TELEGRAM_BOT_TOKEN:** Allows full control of the Telegram bot
- **ANTHROPIC_API_KEY:** Charges to your Anthropic account
- **Never log API keys** in plaintext
- **Never commit** .env to version control

### User Authorization
- Bot restricts access to single Telegram user ID (97566988)
- Unauthorized users receive no response
- Authorization check happens in `_is_authorized()` in [bot.py](src/financial_advisor/bot.py)

### Financial Data
- User holdings and financial data are sensitive
- Database contains conversation history (may include personal info)
- No data is sent to external services except:
  - Telegram (for messaging)
  - Anthropic (for AI responses - subject to their privacy policy)
  - yfinance (for market data - public information only)

## Performance Notes

### Response Times
- Simple commands: <1 second
- AI responses: 2-5 seconds (depends on Claude API latency)
- Market briefings: 5-10 seconds (multiple stock quotes + AI summary)

### Resource Usage
- **Memory:** ~50-100MB (Python + libraries)
- **CPU:** Minimal (mostly I/O-bound)
- **Disk:** SQLite database grows slowly (~1KB per message)
- **Network:** Moderate (polling Telegram API every few seconds)

### Optimization Opportunities
- Switch to webhook mode (reduces Telegram API polling)
- Cache market data (reduce yfinance calls)
- Batch stock quotes (fewer API requests)
- Use connection pooling for database

## Future Feature Ideas

Track potential enhancements in [project_dev_log.md](project_dev_log.md):
- Multi-user support with per-user profiles
- Portfolio transaction logging and history
- Historical performance tracking and analytics
- Integration with brokerage APIs (Robinhood, E*TRADE, etc.)
- Custom alerts for price movements or portfolio events
- Tax loss harvesting recommendations
- Automated rebalancing suggestions
- Web dashboard for portfolio visualization

## Git Workflow

### Branches
- **main** - Production-ready code
- **v0** - Current active development (V0 release)

### Commits
- Use conventional commit messages
- Test before committing
- Never commit sensitive files (.env, user_profile.json)

### .gitignore
Already configured to exclude:
- .env
- config/user_profile.json
- data/*.db (conversation history)
- data/*.log (log files)
- .venv/
- __pycache__/



## Questions & Decisions

### When to suggest model upgrades?
- User explicitly asks for better analysis
- Complex financial modeling required
- Multi-step reasoning needed
- **Don't suggest proactively** - cost implications

### When to clear conversation history?
- User requests with `/clear` command
- Context becomes confusing or outdated
- Database file grows too large (>100MB)
- Never clear automatically - user data is valuable

### When to modify user profile?
- User explicitly requests changes
- Always backup existing profile first
- Validate JSON before saving
- Consider asking user to edit directly (they know their data best)

## Useful Commands Reference

```bash
# Install/update dependencies
uv sync --all-extras

# Run all tests
uv run python -m pytest -v

# Run specific test file
uv run python -m pytest tests/test_config.py -v

# Check configuration
uv run python -c "from src.financial_advisor.config import load_settings; print(load_settings())"

# Start bot
uv run python -m financial_advisor.main

# Format code
uv run ruff format .

# Lint code
uv run ruff check .

# Check logs
tail -f data/bot.log

# Find bot process
ps aux | grep financial_advisor

# Check Python version
python --version

# Check uv version
uv --version
```

---

**Last Updated:** 2026-02-16 (V0 Launch)
**Maintained By:** Project owner + Claude Code
**Version:** 0.1.0
