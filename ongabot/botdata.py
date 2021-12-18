"""This module contains functions to handle bot_data."""
import logging
from typing import Dict

from telegram import Message

from event import Event
from utils.log import log


_logger = logging.getLogger(__name__)


@log
def add_event(bot_data: Dict, key: str, value: Event) -> bool:
    """Add an item to bot_data"""
    if bot_data.get(key):
        _logger.error("key=%s already exist in bot_data!", key)
        return False

    bot_data.update({key: value})
    _logger.debug("bot_data:\n%s", bot_data)
    return True


@log
def get_event(bot_data: Dict, key: str) -> Event:
    """Get an item from bot_data"""
    if not bot_data:
        return None

    if bot_data.get(key) is None:
        _logger.error("key=%s doesn't exist in bot_data!", key)
        return None

    return bot_data.get(key)


@log
def add_pinned_event_poll_message(bot_data: Dict, key: str, value: Message) -> bool:
    """Add a pinned event poll message for a specific chat"""
    if bot_data.get("chat_data") is None:
        bot_data["chat_data"] = {}

    chat_data = bot_data.get("chat_data")
    if chat_data.get(key):
        _logger.error("key=%s already exist in bot_data['chat_data']!", key)
        return False

    chat_data.update({key: value})
    _logger.debug("chat_data:\n%s", chat_data)
    _logger.debug("bot_data:\n%s", bot_data)
    return True


@log
def get_pinned_event_poll_message(bot_data: Dict, key: str) -> Message:
    """Get a pinned event poll message for a specific chat"""
    if not bot_data:
        return None

    chat_data = bot_data.get("chat_data")
    if not chat_data:
        return None

    return chat_data.get(key)


@log
def remove_pinned_event_poll_message(bot_data: Dict, key: str) -> None:
    """Remove a pinned event poll message for a specific chat"""
    if not bot_data:
        return

    chat_data = bot_data.get("chat_data")
    if not chat_data:
        return

    if chat_data.get(key):
        chat_data.pop(key)

    _logger.debug("chat_data:\n%s", chat_data)
    _logger.debug("bot_data:\n%s", bot_data)
