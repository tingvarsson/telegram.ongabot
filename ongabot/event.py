"""This module contains the Event class."""

import logging
from datetime import date, time
from typing import Dict, Optional, Set


from telegram import Bot, Poll, PollAnswer, User
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown

from eventdata import EventData
from utils import log

_logger = logging.getLogger(__name__)


def parse_event_date_from_poll_question(question: str) -> Optional[date]:
    """Parse the event date from a poll question produced by _create_poll_text.

    Format: "Event: <name>\nWhen: YYYY-MM-DD HH:MM"
    Returns the event date on success, None on any parse failure.
    """
    try:
        for line in question.splitlines():
            if line.startswith("When: "):
                date_str = line.removeprefix("When: ").split(" ", 1)[0]
                return date.fromisoformat(date_str)
        return None
    except (ValueError, IndexError):
        return None


class Event:
    """
    The Event object represent an event and its poll

    Args:
        chat_id: id of the chat the event belongs to
        poll: initial telegram.Poll related to the event
        data: date, start time, and slot count for this event

    Attributes:
        chat_id: id of the chat the event belongs to
        poll: telegram.Poll object related to the event
        poll_id: id of the poll object
        poll_answers: dict of users and their answers to the poll
        status_message_id: id of the status message for the event
        data: EventData grouping event_date, start_time, num_slots
        completed: whether the event is complete (date has passed or was cancelled)
        user_streaks: response streak per user id - consecutive most-recent events answered
        user_played_streaks: played streak per user id - consecutive most-recent events in
            which the user picked an actual time slot; this is what the status message stars
        cs2_played: user id -> True for each linked member seen in a real CS2 match on this
            event's date. ONGAbot's own derived fact; no Leetify data is ever stored here.
        cs2_reported: whether the CS2 results message has been posted, so the sweep job that
            posts it never posts twice
    """

    def __init__(self, chat_id: int, poll: Poll, data: EventData) -> None:
        self.chat_id = chat_id
        self.poll = poll
        self.poll_id = poll.id
        self.poll_answers: Dict[User, PollAnswer] = {}
        self.first_answer: Optional[User] = None
        self.status_message_id = 0
        self.data: EventData = data
        self.completed: bool = False
        self.cancelled: bool = False
        self.user_streaks: Dict[int, int] = {}
        self.user_played_streaks: Dict[int, int] = {}
        self.cs2_played: Dict[int, bool] = {}
        self.cs2_reported: bool = False

    @property
    def event_date(self) -> date:
        """Date of this event."""
        return self.data.event_date

    @property
    def start_time(self) -> time:
        """Start time of the first poll option."""
        return self.data.start_time

    @property
    def num_slots(self) -> int:
        """Number of 40-min time slots in the poll."""
        return self.data.num_slots

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state)
        # Set default values for any missing attributes (for backward compatibility with older persisted data)
        if not hasattr(self, "data"):
            # Try to recover the real date/time from the poll question before falling back to date.min.
            # self.poll is always present on old events (it predates EventData).
            parsed_date = parse_event_date_from_poll_question(self.poll.question)
            if parsed_date is not None:
                _logger.info(
                    "Recovered event date from poll question for poll_id=%s: date=%s",
                    self.poll_id,
                    parsed_date,
                )
                self.data = EventData(parsed_date)
            else:
                # date.min treated as already past, so that old events will be marked completed immediately on update
                # and not show up as active events
                _logger.warning(
                    "Could not parse EventData from poll question for poll_id=%s; falling back to date.min",
                    self.poll_id,
                )
                self.data = EventData(date.min)
        if not hasattr(self, "completed"):
            # Assume old events are completed, aligned with date.min, to avoid showing them as active events after
            # a bot update
            self.completed = True
        if not hasattr(self, "cancelled"):
            self.cancelled = False
        if not hasattr(self, "user_streaks"):
            self.user_streaks = {}
        if not hasattr(self, "user_played_streaks"):
            self.user_played_streaks = {}
        if not hasattr(self, "cs2_played"):
            self.cs2_played = {}
        if not hasattr(self, "cs2_reported"):
            # Events that predate CS2 results are never swept - their matches have long since
            # fallen out of Leetify's ~4.5-month history window anyway.
            self.cs2_reported = False

    def __repr__(self) -> str:
        return str(self.__class__) + ": " + str(self.__dict__)

    @log.method
    async def send_status_message(self, bot: Bot) -> None:
        """Send status message for the event poll"""
        chat_member_count = await bot.get_chat_member_count(self.chat_id)
        status_message = await bot.send_message(
            chat_id=self.chat_id,
            text=self._create_status_message_text(chat_member_count),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        self.status_message_id = status_message.message_id

    @log.method
    async def update_status_message(self, bot: Bot) -> None:
        """Update status message for the event poll"""
        chat_member_count = await bot.get_chat_member_count(self.chat_id)
        await bot.edit_message_text(
            chat_id=self.chat_id,
            message_id=self.status_message_id,
            text=self._create_status_message_text(chat_member_count),
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    @log.method
    def mark_complete(self) -> None:
        """Mark this event as completed (date has passed or was cancelled)"""
        self.completed = True

    @log.method
    def record_cs2_session(self, played_user_ids: Set[int]) -> None:
        """Record which linked members were seen playing, and mark the CS2 results as posted.

        Only these derived booleans are persisted - the Leetify scoreboard behind them is
        rendered into the message and discarded.
        """
        self.cs2_played = {user_id: True for user_id in played_user_ids}
        self.cs2_reported = True
        _logger.info(
            "Recorded CS2 session for poll_id=%s: %d member(s) played",
            self.poll_id,
            len(played_user_ids),
        )

    @log.method
    def _create_status_message_text(self, chat_member_count: int) -> str:
        """Create formatted status message text for the event poll"""
        if self.completed:
            message = "*__Event complete\\!__*\n"
        else:
            # total minus (voters + 'me, the bot')
            no_vote_count = chat_member_count - (self.poll.total_voter_count + 1)
            message = f"*__Currently {no_vote_count} non\\-voting infidels\\!__*\n"

        if self.first_answer:
            message += "\n*Honerable mention, first newb to the poll box:* "
            message += f"{self.first_answer.mention_markdown_v2()}\n"

        for i, option in enumerate(self.poll.options):
            message += f"\n*{escape_markdown(option.text, version=2)} \\({option.voter_count}\\)*"
            for user, answer in self.poll_answers.items():
                if i in answer.option_ids:
                    # The star is the played streak (consecutive events with an actual slot
                    # pick), not the response streak - showing up is what earns the star.
                    streak = self.user_played_streaks.get(user.id, 0)
                    streak_suffix = f" ★{streak}" if streak > 1 else ""
                    message += f"\n  • {user.mention_markdown_v2()}{streak_suffix}"
            message += "\n"

        return message

    @log.method
    def update_poll(self, poll: Poll) -> None:
        """Update poll information"""
        self.poll = poll
        _logger.debug("%s", self)

    @log.method
    def update_answer(self, poll_answer: PollAnswer) -> None:
        """Update, or add, an answer for a specific user"""
        if poll_answer.user is None:
            _logger.warning("Attempted to update answer for user with None ID")
            return

        if self.first_answer is None:
            self.first_answer = poll_answer.user

        self.poll_answers[poll_answer.user] = poll_answer
        _logger.debug("%s", self)
