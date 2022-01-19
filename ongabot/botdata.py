"""This module contains the BotData class."""
import logging
from typing import Callable, Dict

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
        chats: dictionary of Chat objects index on chat_id
        events: dictionary of Event objects index on poll_id
    """

    def __init__(self) -> None:
        self.chats: Dict[int, Chat] = {}
        self.events: Dict[str, Event] = {}

    def __repr__(self) -> str:
        return str(self.__class__) + ": " + str(self.__dict__)

    @log.method
    def add_chat(self, chat: Chat) -> bool:
        """Add a Chat to BotData"""
        if self.chats.get(chat.chat_id):
            _logger.error("Chat with chat_id=%s already exist in BotData!", chat.chat_id)
            return False

        self.chats.update({chat.chat_id: chat})
        return True

    @log.method
    def get_chat(self, chat_id: int) -> Chat:
        """Get a Chat from BotData"""
        # Create a Chat object for chat_id if not found
        if not self.chats.get(chat_id):
            self.chats.update({chat_id: Chat(chat_id)})

        return self.chats.get(chat_id)

    @log.method
    def remove_chat(self, chat_id: int) -> None:
        """Remove a Chat from BotData"""
        if self.chats.get(chat_id):
            self.chats.pop(chat_id)

    @log.method
    def add_event(self, event: Event) -> bool:
        """Add an Event to BotData"""
        if self.events.get(event.poll_id):
            _logger.error("Event with poll_id=%s already exist in BotData!", event.poll_id)
            return False

        self.events.update({event.poll_id: event})
        return True

    @log.method
    def get_event(self, poll_id: str) -> Event:
        """Get an event from BotData"""

        if not self.events.get(poll_id):
            _logger.error("Event with poll_id=%s doesn't exist in BotData!", poll_id)
            return None

        return self.events.get(poll_id)

    @log.method
    def remove_event(self, poll_id: str) -> None:
        """Remove an event from BotData"""
        if self.events.get(poll_id):
            self.events.pop(poll_id)

    @log.method
    def schedule_all_event_jobs(self, job_queue: JobQueue, callback: Callable) -> None:
        """Schedule all event jobs, in all chats"""
        for chat in self.chats.values():
            chat.schedule_all_event_jobs(job_queue, callback)
