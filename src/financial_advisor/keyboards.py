"""Telegram inline keyboard builders for V1 navigation."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main navigation keyboard shown with /start and /portfolio."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Portfolio", callback_data="portfolio"),
            InlineKeyboardButton("📈 Analysis", callback_data="analysis"),
        ],
        [
            InlineKeyboardButton("📋 Briefing", callback_data="briefing"),
            InlineKeyboardButton("❓ Help", callback_data="help"),
        ],
    ])


def portfolio_keyboard() -> InlineKeyboardMarkup:
    """Keyboard shown after portfolio summary."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📈 Allocation", callback_data="analysis"),
            InlineKeyboardButton("🔄 Refresh", callback_data="portfolio"),
        ],
        [
            InlineKeyboardButton("📋 Briefing", callback_data="briefing"),
            InlineKeyboardButton("🏠 Menu", callback_data="menu"),
        ],
    ])
