"""This module contains the BotData class."""

import logging
from typing import Callable, Dict, Set

from telegram.ext import JobQueue

from chat import Chat
from event import Event
from utils import log

_logger = logging.getLogger(__name__)


class BotData:
    """
    The BotData object represent all persistent data stored for the bot

    Args:

    Attributes:
        chats: Dict of Chat objects indexed by chat_id
        authorized_chats: Set of chat IDs allowed to use the bot
    """

    def __init__(self) -> None:
        self.chats: Dict[int, Chat] = {}
        self.authorized_chats: Set[int] = set()

    def __setstate__(self, state: Dict) -> None:
        self.__dict__.update(state)
        if not hasattr(self, "authorized_chats"):
            self.authorized_chats = set()

    def __repr__(self) -> str:
        return str(self.__class__) + ": " + str(self.__dict__)

    @log.method
    def get_chat(self, chat_id: int) -> Chat:
        """Get a Chat from BotData, and if it doesnt exist create it"""
        if not self.chats.get(chat_id):
            # Create a Chat object for chat_id if not found
            self.chats.update({chat_id: Chat(chat_id)})

        return self.chats.get(chat_id)

    @log.method
    def get_event(self, poll_id: str) -> Event:
        """Get an event from BotData"""
        for chat in self.chats.values():
            event = chat.get_event(poll_id)
            if event:
                return event

        _logger.error("Event with poll_id=%s doesn't exist in BotData!", poll_id)
        return None

    @log.method
    def is_authorized(self, chat_id: int) -> bool:
        """Return True if the chat is authorized to use the bot"""
        return chat_id in self.authorized_chats

    @log.method
    def authorize_chat(self, chat_id: int) -> None:
        """Add a chat to the set of authorized chats"""
        self.authorized_chats.add(chat_id)
        _logger.info("Authorized chat_id=%s", chat_id)

    @log.method
    def deauthorize_chat(self, chat_id: int) -> None:
        """Remove a chat from the set of authorized chats"""
        self.authorized_chats.discard(chat_id)
        _logger.info("Deauthorized chat_id=%s", chat_id)

    @log.method
    def schedule_all_event_jobs(self, job_queue: JobQueue, callback: Callable) -> None:
        """Schedule all event jobs, in all chats"""
        for chat in self.chats.values():
            chat.schedule_event_job(job_queue, callback)
