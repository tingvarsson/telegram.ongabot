"""This module contains the Chat class."""

import logging
from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional, cast
from zoneinfo import ZoneInfo

from telegram import Message, User
from telegram.error import TelegramError
from telegram.ext import Job, JobQueue

from event import Event, parse_event_date_from_poll_question
from eventjob import EventJob
from utils import clock, log
from verification import VerificationVote

_logger = logging.getLogger(__name__)

# How long a posted Short is remembered, so /short does not repeat one within this window.
SHORTS_HISTORY_DAYS = 30
# How many closed /unverify and /verify poll ids are remembered, see pop_verification_vote.
CLOSED_VERIFICATION_POLLS_KEPT = 10


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
        recent_video_ids: video_id -> date posted, for /short's 30-day no-repeat
        unverified: user_id -> first name of each member voted unverified (see verification.py)
        verification_votes: open /unverify and /verify votes indexed on poll_id
        closed_verification_polls: poll_ids of the most recently closed votes, newest last
        timezone_name: IANA zone set with /timezone, or None to follow the bot default
            (BOT_TIMEZONE), so a later change to that default still reaches this chat
    """

    def __init__(self, chat_id: int) -> None:
        self.chat_id = chat_id
        self.events: Dict[date, Event] = {}
        self._poll_id_index: Dict[str, date] = {}
        self.event_job: Optional[EventJob] = None
        self.pinned_polls: Dict[str, Message] = {}
        self.recent_video_ids: Dict[str, date] = {}
        self.unverified: Dict[int, str] = {}
        self.verification_votes: Dict[str, VerificationVote] = {}
        self.closed_verification_polls: List[str] = []
        self.timezone_name: Optional[str] = None

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
            # Unpickled legacy state still has poll_id (str) keys here, which the isinstance
            # check above has just confirmed; cast so the migration can read them as such.
            old_events = cast(Dict[str, Event], self.events)
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

        self._recover_sentinel_dates()

        # Rebuild secondary index if missing or empty
        if not hasattr(self, "_poll_id_index") or not self._poll_id_index:
            self._poll_id_index = {e.poll_id: e.event_date for e in self.events.values()}

        self._migrate_shorts_state()
        self._default_verification_state()
        # Pickles from before /timezone follow the bot default.
        self.__dict__.setdefault("timezone_name", None)

    def __repr__(self) -> str:
        return str(self.__class__) + ": " + str(self.__dict__)

    @property
    def tz(self) -> ZoneInfo:
        """The zone this chat's times are in: its own /timezone, else the bot default.

        A stored zone the zone database no longer knows (renamed in a tzdata update, say) logs
        a warning and falls back to the bot default rather than breaking every job for the chat.
        """
        if self.timezone_name:
            try:
                return clock.resolve_timezone(self.timezone_name)
            except ValueError:
                _logger.warning(
                    "chat_id=%s has unknown timezone %r; using the bot default", self.chat_id, self.timezone_name
                )
        return clock.bot_timezone()

    def now(self) -> datetime:
        """The current time in this chat's zone, timezone-aware."""
        return clock.now(self.tz)

    def today(self) -> date:
        """The current date in this chat's zone."""
        return clock.today(self.tz)

    @log.method
    def set_timezone(self, name: Optional[str]) -> None:
        """Set this chat's zone by canonical IANA name, or None to follow the bot default again."""
        _logger.info("Timezone for chat_id=%s changed from %s to %s", self.chat_id, self.timezone_name, name)
        self.timezone_name = name

    def _default_verification_state(self) -> None:
        """Default the /unverify and /verify state missing from pickles written before it existed."""
        if not hasattr(self, "unverified"):
            self.unverified = {}
        if not hasattr(self, "verification_votes"):
            self.verification_votes = {}
        if not hasattr(self, "closed_verification_polls"):
            self.closed_verification_polls = []

    def _migrate_shorts_state(self) -> None:
        """Drop the daily-Short state that /short no longer uses and default recent_video_ids.

        Pickles written before /short became on-demand carry topic_scores, posted_shorts and
        last_shorts_posted_date; only recent_video_ids (the no-repeat window) is still used.
        """
        stale = [k for k in ("topic_scores", "posted_shorts", "last_shorts_posted_date") if k in self.__dict__]
        for key in stale:
            del self.__dict__[key]
        if stale:
            _logger.debug("Dropped stale shorts state %s for chat_id=%s", stale, self.__dict__.get("chat_id"))
        if not hasattr(self, "recent_video_ids"):
            self.recent_video_ids = {}

    def _recover_sentinel_dates(self) -> None:
        """Retroactively recover real dates for events saved with sentinel dates.

        Handles events stuck at date.min or surrogate keys (year == 1) by the broken
        pre-fix v1.1.0 migration that saved date.min without parsing poll questions.
        Rebuilds _poll_id_index if any events were re-keyed.
        """
        # year == 1 covers date.min (0001-01-01) and all surrogate keys (0001-01-02, etc.)
        # assigned during the broken v1.1.0 migration; real events will never fall in year 1.
        sentinel_items = [(d, e) for d, e in list(self.events.items()) if d.year == 1]
        if not sentinel_items:
            return
        for sentinel_date, event in sentinel_items:
            try:
                question = event.poll.question
            except AttributeError:
                _logger.warning("Sentinel event poll_id=%s has no poll; skipping recovery", event.poll_id)
                continue
            real_date = parse_event_date_from_poll_question(question)
            if real_date is not None and real_date.year != 1:
                if real_date not in self.events:
                    del self.events[sentinel_date]
                    event.data.event_date = real_date
                    self.events[real_date] = event
                    _logger.info(
                        "Retroactively recovered date=%s for poll_id=%s (was sentinel date=%s)",
                        real_date,
                        event.poll_id,
                        sentinel_date,
                    )
                else:
                    _logger.warning(
                        "Cannot retroactively recover date=%s for poll_id=%s: date already occupied",
                        real_date,
                        event.poll_id,
                    )
        self._poll_id_index = {e.poll_id: e.event_date for e in self.events.values()}

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

    def is_recently_posted(self, video_id: str) -> bool:
        """True when video_id was posted as a /short in this chat within SHORTS_HISTORY_DAYS."""
        return video_id in self.recent_video_ids

    @log.method
    def record_shorts_post(self, video_id: str, posted_at: datetime) -> None:
        """Remember a posted Short so /short does not repeat it within SHORTS_HISTORY_DAYS."""
        self.recent_video_ids[video_id] = posted_at.date()
        self._prune_shorts_history(posted_at.date())

    @log.method
    def forget_shorts_post(self, video_id: str) -> None:
        """Undo record_shorts_post for a Short that could not be sent after all."""
        self.recent_video_ids.pop(video_id, None)

    def _prune_shorts_history(self, today: date) -> None:
        """Drop no-repeat entries older than SHORTS_HISTORY_DAYS, so the history stays bounded."""
        cutoff = today - timedelta(days=SHORTS_HISTORY_DAYS)
        self.recent_video_ids = {v: d for v, d in self.recent_video_ids.items() if d >= cutoff}

    def is_unverified(self, user_id: int) -> bool:
        """True when the group has voted user_id unverified."""
        return user_id in self.unverified

    @log.method
    def set_unverified(self, user_id: int, name: str, unverified: bool) -> None:
        """Mark user_id unverified under name, or verified again."""
        if unverified:
            self.unverified[user_id] = name
        else:
            self.unverified.pop(user_id, None)
        _logger.info("Set user_id=%s unverified=%s in chat_id=%s", user_id, unverified, self.chat_id)

    def open_vote_for(self, user_id: int) -> Optional[VerificationVote]:
        """The open /unverify or /verify vote on user_id, if there is one."""
        return next((v for v in self.verification_votes.values() if v.target_id == user_id), None)

    @log.method
    def add_verification_vote(self, vote: VerificationVote) -> None:
        """Store an open /unverify or /verify vote until it closes."""
        self.verification_votes[vote.poll_id] = vote

    @log.method
    def pop_verification_vote(self, poll_id: str) -> Optional[VerificationVote]:
        """Remove and return the open vote for poll_id, or None if there is none.

        The poll_id is remembered in closed_verification_polls: stopping the poll makes
        Telegram send one last poll update, which must still be recognised as a vote.
        """
        vote = self.verification_votes.pop(poll_id, None)
        if vote is not None:
            self.closed_verification_polls.append(poll_id)
            # A stopped poll gets no further updates, so only the last few need remembering.
            del self.closed_verification_polls[:-CLOSED_VERIFICATION_POLLS_KEPT]
        return vote

    def has_verification_poll(self, poll_id: str) -> bool:
        """True when poll_id is an open or recently closed /unverify or /verify vote."""
        return poll_id in self.verification_votes or poll_id in self.closed_verification_polls

    def find_user_by_username(self, username: str) -> Optional[User]:
        """Find a member by @username among everyone who has voted on this chat's events.

        The Bot API cannot look a user up by username, so this is the only way to resolve an
        @mention of someone who is not replied to. Newest events first, so the latest User
        object (and name) wins.
        """
        wanted = username.lstrip("@").casefold()
        for event_date in sorted(self.events, reverse=True):
            for user in self.events[event_date].poll_answers:
                if user.username and user.username.casefold() == wanted:
                    return user
        return None

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
    def schedule_event_job(
        self, job_queue: JobQueue, callback: Callable, now: Optional[datetime] = None
    ) -> Optional[Job]:
        """Schedule the event job, if there is one, in this chat's zone.

        Also creates a poll right away when the weekly trigger passed while the bot was down
        (a restart on Sunday evening after 20:00, say) and that week's event has no poll yet.
        Returns the weekly job, or None when the chat has no schedule.
        """
        if not self.event_job:
            return None

        job = self.event_job.schedule(job_queue, callback, self.tz)

        missed = self.event_job.missed_event_date(now or self.now())
        if missed is not None and self.get_event_by_date(missed) is None:
            _logger.info(
                "Weekly trigger for chat_id=%s was missed (last run %s); creating the poll for %s now",
                self.chat_id,
                self.event_job.last_triggered_on,
                missed,
            )
            # A few seconds out, like the other startup jobs: at boot the scheduler only starts
            # after polling does, and a job overdue by more than APScheduler's one-second
            # misfire grace would be dropped.
            job_queue.run_once(callback, when=5, chat_id=self.chat_id, name=f"{self.event_job.job_name}_catchup")
        return job
