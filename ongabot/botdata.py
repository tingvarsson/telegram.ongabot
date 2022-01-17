"""This module contains functions to handle bot_data."""
import logging
from typing import Dict

from telegram import Message

from event import Event
from utils.log import log


_logger = logging.getLogger(__name__)


@log
def add_event(bot_data: Dict, poll_id: str, event: Event) -> bool:
    """Add an item to bot_data"""
    if bot_data.get(poll_id):
        _logger.error("poll_id=%s already exist in bot_data!", poll_id)
        return False

    bot_data.update({poll_id: event})
    _logger.debug("bot_data:\n%s", bot_data)
    return True


@log
def get_event(bot_data: Dict, poll_id: str) -> Event:
    """Get an item from bot_data"""
    if not bot_data:
        return None

    if not bot_data.get(poll_id):
        _logger.error("poll_id=%s doesn't exist in bot_data!", poll_id)
        return None

    return bot_data.get(poll_id)


@log
def add_pinned_event_poll_message(bot_data: Dict, chat_id: int, message: Message) -> bool:
    """Add a pinned event poll message for a specific chat"""
    if not bot_data.get("chats"):
        bot_data.update({"chats": {}})

    chats = bot_data.get("chats")
    if not chats.get(chat_id):
        chats.update({chat_id: {}})

    chat_data = chats.get(chat_id)
    if chat_data.get("poll_message"):
        _logger.error("poll_message already exist in chats[chat_id=%s]!", chat_id)
        return False

    chat_data.update({"poll_message": message})
    _logger.debug("chats[chat_id=%s]:\n%s", chat_id, chat_data)
    return True


@log
def get_pinned_event_poll_message(bot_data: Dict, chat_id: int) -> Message:
    """Get a pinned event poll message for a specific chat"""
    if not bot_data:
        return None

    chats = bot_data.get("chats")
    if not chats:
        return None

    chat_data = chats.get(chat_id)
    if not chat_data:
        return None

    return chat_data.get("poll_message")


@log
def remove_pinned_event_poll_message(bot_data: Dict, chat_id: int) -> None:
    """Remove a pinned event poll message for a specific chat"""
    if not bot_data:
        return

    chats = bot_data.get("chats")
    if not chats:
        return

    chat_data = chats.get(chat_id)
    if not chat_data:
        return

    if chat_data.get("poll_message"):
        chat_data.pop("poll_message")

    _logger.debug("chats[chat_id=%s]:\n%s", chat_id, chat_data)


@log
def add_event_job(bot_data: Dict, chat_id: int, job_name: str, day_to_schedule: str) -> bool:
    """abc"""
    if not bot_data.get("chats"):
        bot_data.update({"chats": {}})

    chats = bot_data.get("chats")
    if not chats.get(chat_id):
        chats.update({chat_id: {}})

    chat_data = chats.get(chat_id)
    if not chat_data.get("jobs"):
        chat_data.update({"jobs": {}})

    jobs = chat_data.get("jobs")
    if jobs.get(job_name):
        _logger.error("job_name=%s already exist in chats[chat_id=%s]!", job_name, chat_id)
        return False

    jobs.update({job_name: {"day_to_schedule": day_to_schedule}})
    _logger.debug("jobs[job_name=%s]:\n%s", job_name, jobs[job_name])
    _logger.debug("chats[chat_id=%s]:\n%s", chat_id, chat_data)
    return True


@log
def remove_event_job(bot_data: Dict, chat_id: int, job_name: str) -> None:
    """abc"""
    if not bot_data:
        return

    chats = bot_data.get("chats")
    if not chats:
        return

    chat_data = chats.get(chat_id)
    if not chat_data:
        return

    jobs = chat_data.get("jobs")
    if not jobs:
        return

    if jobs.get(job_name):
        jobs.pop(job_name)

    _logger.debug("jobs:\n%s", jobs)
    _logger.debug("chats[chat_id=%s]:\n%s", chat_id, chat_data)
