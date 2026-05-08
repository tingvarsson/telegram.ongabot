"""This module contains the Chat class."""

import logging
from datetime import date
from typing import Callable, Dict, Optional

from telegram import Message
from telegram.error import TelegramError
from telegram.ext import JobQueue

from event import Event
from eventjob import EventJob
from utils import log

_logger = logging.getLogger(__name__)


class Chat:
    """
    The Chat object represents a chat and related data

    Args:
        chat_id: id of the chat the data belongs to

    Attributes:
        chat_id: id of the chat the data belongs to
        events: dictionary of Event objects indexed on poll_id
        event_job: EventJob if there is one scheduled for the chat, otherwise None
        pinned_polls: dict of pinned event poll messages indexed on poll_id
    """

    def __init__(self, chat_id: int) -> None:
        self.chat_id = chat_id

        self.events: Dict[str, Event] = {}
        self.event_job: Optional[EventJob] = None
        self.pinned_polls: Dict[str, Message] = {}

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state)
        # Set default values for any missing attributes (for backward compatibility with older persisted data)
        if not hasattr(self, "pinned_polls"):
            old = self.__dict__.pop("pinned_poll", None)
            self.pinned_polls = {}
            if old is not None:
                try:
                    self.pinned_polls[old.poll.id] = old
                except AttributeError:
                    pass  # old message had no .poll; discard silently

        # Remove old pinned_poll attribute if it exists, to avoid confusion and save memory
        self.__dict__.pop("pinned_poll", None)

    def __repr__(self) -> str:
        return str(self.__class__) + ": " + str(self.__dict__)

    @property
    def active_events(self) -> list[Event]:
        """Return a list of active (not completed) events."""
        return [e for e in self.events.values() if not e.completed]

    def find_active_event(self, target_date: date) -> list[Event]:
        """Return active events matching target_date."""
        return [e for e in self.active_events if e.event_date == target_date]

    @log.method
    def add_event(self, event: Event) -> bool:
        """Add an Event"""
        if self.events.get(event.poll_id):
            _logger.error("Event with poll_id=%s already exist!", event.poll_id)
            return False

        self.events.update({event.poll_id: event})
        return True

    @log.method
    def get_event(self, poll_id: str) -> Optional[Event]:
        """Get an event"""

        if not self.events.get(poll_id):
            _logger.error("Event with poll_id=%s doesn't exist!", poll_id)
            return None

        return self.events.get(poll_id)

    @log.method
    def set_pinned_poll(self, poll_id: str, message: Message) -> bool:
        """Register a pinned poll message for a given poll_id"""
        if poll_id in self.pinned_polls:
            _logger.error(
                "pinned_poll for poll_id=%s already exists when adding message_id=%s",
                poll_id,
                message.message_id,
            )
            return False

        self.pinned_polls[poll_id] = message
        return True

    @log.method
    async def remove_pinned_poll(self, poll_id: str) -> None:
        """Unpin and remove the pinned event poll message for a given poll_id"""
        message = self.pinned_polls.get(poll_id)
        if message is None:
            _logger.warning("Trying to remove pinned_poll for unknown poll_id=%s", poll_id)
            return

        try:
            await message.unpin()
        except TelegramError:
            _logger.warning(
                "Failed trying to unpin message_id=%i for poll_id=%s",
                message.message_id,
                poll_id,
            )
        del self.pinned_polls[poll_id]

    @log.method
    def set_event_job(self, event_job: EventJob) -> bool:
        """Set an event job for the chat"""
        if self.event_job:
            _logger.error("job_name=%s already exist Chat with chat_id=%s!", event_job.job_name, self.chat_id)
            return False

        self.event_job = event_job
        return True

    @log.method
    def remove_event_job(self, job_queue: JobQueue) -> bool:
        """Remove the event job"""
        if not self.event_job:
            _logger.debug("Trying to remove event_job=None")
            return False

        result = self.event_job.deschedule(job_queue)
        self.event_job = None
        return result

    @log.method
    def schedule_event_job(self, job_queue: JobQueue, callback: Callable) -> None:
        """Schedule the event job if it exist"""
        if self.event_job:
            self.event_job.schedule(job_queue, callback)
