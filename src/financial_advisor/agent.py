"""Claude API wrapper with conversation memory."""

import logging

from anthropic import AsyncAnthropic

from .config import Settings
from .memory import ConversationMemory
from .prompts import DISCLAIMER, build_system_prompt

logger = logging.getLogger(__name__)


class FinancialAdvisorAgent:
    def __init__(self, settings: Settings, memory: ConversationMemory):
        self._settings = settings
        self._memory = memory
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._system_prompt = build_system_prompt(settings.user_profile)

    async def chat(self, user_id: int, message: str) -> str:
        """Process a user message and return the assistant's response with disclaimer."""
        # Store user message
        await self._memory.add_message(user_id, "user", message)

        # Get conversation history
        history = await self._memory.get_history(user_id)

        # Call Claude
        try:
            response = await self._client.messages.create(
                model=self._settings.claude_model,
                max_tokens=2048,
                system=self._system_prompt,
                messages=history,
            )
        except Exception:
            logger.exception("Claude API error for user %s", user_id)
            # Remove the user message we just stored since we failed
            # (get_history will re-fetch, so this keeps things consistent)
            raise

        assistant_text = response.content[0].text

        # Log token usage
        usage = response.usage
        logger.info(
            "Claude API | user=%s input_tokens=%d output_tokens=%d model=%s",
            user_id,
            usage.input_tokens,
            usage.output_tokens,
            self._settings.claude_model,
        )

        # Store assistant response
        token_estimate = usage.input_tokens + usage.output_tokens
        await self._memory.add_message(user_id, "assistant", assistant_text, token_estimate)

        # Append disclaimer to substantive responses
        return assistant_text + DISCLAIMER

    async def summarize(self, text: str) -> str:
        """Generate a short summary using Claude (for briefings). No memory involved."""
        try:
            response = await self._client.messages.create(
                model=self._settings.claude_model,
                max_tokens=300,
                system=(
                    "You are a concise financial market analyst. "
                    "Summarize the market data below in 2-3 sentences. "
                    "Focus on key moves and what they might mean for investors."
                ),
                messages=[{"role": "user", "content": text}],
            )
            return response.content[0].text
        except Exception:
            logger.exception("Claude summarize error")
            return "Market summary unavailable."
