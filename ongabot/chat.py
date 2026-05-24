"""This module contains the Chat class."""

import logging
from datetime import date, timedelta
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
        events: dictionary of Event objects indexed on event_date
        _poll_id_index: secondary index mapping poll_id to event_date for O(1) lookup
        event_job: EventJob if there is one scheduled for the chat, otherwise None
        pinned_polls: dict of pinned event poll messages indexed on poll_id
    """

    def __init__(self, chat_id: int) -> None:
        self.chat_id = chat_id
        self.events: Dict[date, Event] = {}
        self._poll_id_index: Dict[str, date] = {}
        self.event_job: Optional[EventJob] = None
        self.pinned_polls: Dict[str, Message] = {}

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state)
        # Migrate old pinned_poll → pinned_polls
        if not hasattr(self, "pinned_polls"):
            old = self.__dict__.pop("pinned_poll", None)
            self.pinned_polls = {}
            if old is not None:
                try:
                    self.pinned_polls[old.poll.id] = old
                except AttributeError:
                    pass
        self.__dict__.pop("pinned_poll", None)

        # Migrate events from old Dict[str, Event] to Dict[date, Event]
        if self.events and not isinstance(next(iter(self.events)), date):
            old_events: Dict[str, Event] = self.events
            migrated: Dict[date, Event] = {}
            for _poll_id, event in old_events.items():
                d = event.event_date
                if d in migrated:
                    existing = migrated[d]
                    if existing.completed and not event.completed:
                        _logger.warning(
                            "Date collision during migration: discarding completed poll_id=%s,"
                            " keeping active poll_id=%s for date=%s",
                            existing.poll_id,
                            event.poll_id,
                            d,
                        )
                        migrated[d] = event
                    elif d == date.min:
                        # Real date unknown for both events; assign unique surrogate key to preserve statistics
                        while d in migrated:
                            d += timedelta(days=1)
                        _logger.warning(
                            "Date collision on date.min for poll_id=%s;"
                            " assigning surrogate date=%s to preserve statistics",
                            event.poll_id,
                            d,
                        )
                        migrated[d] = event
                    else:
                        _logger.warning(
                            "Date collision during migration: discarding poll_id=%s for date=%s",
                            event.poll_id,
                            d,
                        )
                else:
                    migrated[d] = event
            self.events = migrated

        # Rebuild secondary index if missing or empty
        if not hasattr(self, "_poll_id_index") or not self._poll_id_index:
            self._poll_id_index = {e.poll_id: e.event_date for e in self.events.values()}

    def __repr__(self) -> str:
        return str(self.__class__) + ": " + str(self.__dict__)

    @property
    def active_events(self) -> list[Event]:
        """Return a list of active (not completed) events."""
        return [e for e in self.events.values() if not e.completed]

    def get_event_by_date(self, target_date: date) -> Optional[Event]:
        """Return the event for target_date, or None if no event exists for that date."""
        return self.events.get(target_date)

    def get_event_by_poll_id(self, poll_id: str) -> Optional[Event]:
        """Return the event for poll_id via the secondary index, or None."""
        event_date = self._poll_id_index.get(poll_id)
        if event_date is None:
            return None
        return self.events.get(event_date)

    @log.method
    def add_event(self, event: Event, force: bool = False) -> bool | None:
        """Add an Event to this chat.

        Returns True on success.
        Returns False if an active (non-completed) event already exists for the date.
        Returns None if a completed (date-passed or cancelled) event exists for the date and force is False.
        With force=True, replaces any existing completed event.
        """
        existing = self.events.get(event.event_date)
        if existing is not None:
            if not existing.completed:
                _logger.error("Active event for date=%s already exists!", event.event_date)
                return False
            if not force:
                _logger.debug("Cancelled event for date=%s exists, force=True required.", event.event_date)
                return None
            self.remove_event(existing.poll_id)

        self.events[event.event_date] = event
        self._poll_id_index[event.poll_id] = event.event_date
        return True

    @log.method
    def remove_event(self, poll_id: str) -> None:
        """Remove an event by poll_id from both the events dict and the secondary index."""
        event_date = self._poll_id_index.get(poll_id)
        if event_date is None:
            _logger.warning("Trying to remove unknown poll_id=%s from events", poll_id)
            return
        self.events.pop(event_date, None)
        self._poll_id_index.pop(poll_id, None)

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
