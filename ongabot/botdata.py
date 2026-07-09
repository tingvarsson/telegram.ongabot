"""This module contains the BotData class."""

import logging
from typing import Callable, Dict, Optional, Set

from telegram.ext import JobQueue

from chat import Chat
from event import Event
from utils import log

_logger = logging.getLogger(__name__)


class BotData:
    """
    The BotData object represent all persistent data stored for the bot

    Attributes:
        chats: Dict of Chat objects indexed by chat_id
        authorized_chats: Set of chat IDs allowed to use the bot
        last_known_version: Version string of the last bot startup, used to detect upgrades
    """

    def __init__(self) -> None:
        self.chats: Dict[int, Chat] = {}
        self.authorized_chats: Set[int] = set()
        self.last_known_version: str | None = None

    def __setstate__(self, state: Dict) -> None:
        self.__dict__.update(state)
        # Set default values for any missing attributes (for backward compatibility with older persisted data)
        if not hasattr(self, "authorized_chats"):
            # Old chats are not authorized by default, to avoid accidentally authorizing all existing chats
            # when deploying the bot with persistence for the first time
            self.authorized_chats = set()
        if not hasattr(self, "last_known_version"):
            # Deployments predating version tracking are seeded with the known starting
            # point (1.2.0, the release in which tracking shipped) instead of None, so
            # the next real release announces the delta rather than recording silently.
            self.last_known_version = "1.2.0"

    def __repr__(self) -> str:
        return str(self.__class__) + ": " + str(self.__dict__)

    @log.method
    def get_chat(self, chat_id: int) -> Chat:
        """Get a Chat from BotData, and if it doesnt exist create it"""
        chat = self.chats.get(chat_id)
        if not chat:
            # Create a Chat object for chat_id if not found
            chat = Chat(chat_id)
            self.chats.update({chat_id: chat})

        return chat

    @log.method
    def get_event(self, poll_id: str) -> Optional[Event]:
        """Get an event from BotData"""
        for chat in self.chats.values():
            event = chat.get_event_by_poll_id(poll_id)
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
