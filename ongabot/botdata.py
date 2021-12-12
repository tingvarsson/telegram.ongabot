"""This module contains functions to handle bot_data."""
import logging
from typing import Dict

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
    if bot_data.get(key) is None:
        _logger.error("key=%s doesn't exist in bot_data!", key)
        return None

    return bot_data[key]
