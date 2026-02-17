"""Tests for keyboards module."""

from telegram import InlineKeyboardMarkup

from financial_advisor.keyboards import main_menu_keyboard, portfolio_keyboard


def test_main_menu_keyboard_returns_markup():
    kb = main_menu_keyboard()
    assert isinstance(kb, InlineKeyboardMarkup)
    assert kb.inline_keyboard is not None
    assert len(kb.inline_keyboard) >= 2


def test_main_menu_keyboard_has_expected_buttons():
    kb = main_menu_keyboard()
    all_buttons = [btn for row in kb.inline_keyboard for btn in row]
    callback_data = [b.callback_data for b in all_buttons]
    assert "portfolio" in callback_data
    assert "briefing" in callback_data
    assert "help" in callback_data or "analysis" in callback_data


def test_portfolio_keyboard_returns_markup():
    kb = portfolio_keyboard()
    assert isinstance(kb, InlineKeyboardMarkup)
    assert len(kb.inline_keyboard) >= 2


def test_portfolio_keyboard_has_refresh_and_menu():
    kb = portfolio_keyboard()
    all_buttons = [btn for row in kb.inline_keyboard for btn in row]
    callback_data = [b.callback_data for b in all_buttons]
    assert "portfolio" in callback_data or "Refresh" in [b.text for b in all_buttons]
    assert "menu" in callback_data or "Menu" in [b.text for b in all_buttons]
