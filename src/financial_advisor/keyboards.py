"""Telegram inline keyboard builders."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main navigation keyboard shown with /start and /portfolio."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📊 Portfolio", callback_data="portfolio"),
                InlineKeyboardButton("📈 Analysis", callback_data="analysis"),
            ],
            [
                InlineKeyboardButton("📋 Briefing", callback_data="briefing"),
                InlineKeyboardButton("❓ Help", callback_data="help"),
            ],
        ]
    )


def portfolio_keyboard() -> InlineKeyboardMarkup:
    """Keyboard shown after portfolio summary."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📈 Allocation", callback_data="analysis"),
                InlineKeyboardButton("🔄 Refresh", callback_data="portfolio"),
            ],
            [
                InlineKeyboardButton("📋 Briefing", callback_data="briefing"),
                InlineKeyboardButton("🏠 Menu", callback_data="menu"),
            ],
        ]
    )


def alert_keyboard(alert_id: int) -> InlineKeyboardMarkup:
    """Inline keyboard for a triggered alert notification."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Acknowledge", callback_data=f"alert_ack_{alert_id}"),
                InlineKeyboardButton("Dismiss", callback_data=f"alert_dismiss_{alert_id}"),
            ],
        ]
    )
