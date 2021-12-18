"""This module contains the Event class."""
import logging
from datetime import date
from typing import Dict

from telegram import Bot, ParseMode, Poll, PollAnswer, TelegramError, User
from telegram.ext import CallbackContext
from telegram.utils.helpers import escape_markdown

import botdata
from utils import helper
from utils import log

_logger = logging.getLogger(__name__)


def create_event(context: CallbackContext, chat_id: str) -> None:
    """abc"""

    # Retrieve previous pinned poll message and try to unpin if applicable
    pinned_poll = context.chat_data.get("pinned_poll_msg")

    if pinned_poll is not None:
        next_wed = helper.get_upcoming_date(date.today(), "wednesday").strftime("%Y-%m-%d")
        if next_wed in pinned_poll.poll.question:
            context.bot.send_message(
                chat_id,
                "Event already exists for: "
                + next_wed
                + "\nSend /cancelevent first if you wish to create a new event.",
            )
            _logger.debug("Event already exist for next Wednesday (%s).", next_wed)
            return

        try:
            pinned_poll.unpin()
        except TelegramError:
            _logger.warning(
                "Failed trying to unpin message (message_id=%i).", pinned_poll.message_id
            )
        context.chat_data["pinned_poll_msg"] = None

    poll_message = context.bot.send_poll(
        chat_id,
        create_poll_text(),
        options=create_poll_options(),
        is_anonymous=False,
        allows_multiple_answers=True,
    )
    _logger.debug("poll_message:\n%s", poll_message)

    event = Event(chat_id, poll_message.poll)
    event.send_status_message(context.bot)

    botdata.add_event(context.bot_data, key=event.poll_id, value=event)

    # Pin new message and save to chat_data for future removal
    poll_message.pin(disable_notification=True)
    context.chat_data["pinned_poll_msg"] = poll_message
    _logger.debug("pinned_poll_msg: %s", poll_message.poll.id)


def create_poll_text() -> str:
    """Create text field for poll"""
    title = "Event: ONGA"
    when = f"When: {helper.get_upcoming_date(date.today(), 'wednesday')}"
    text = f"{title}\n{when}"
    return text


def create_poll_options() -> list[str]:
    """Create options for poll"""
    options = [
        "18.00",
        "19.00",
        "20.00",
        "21.00",
        "No-op",
        "Maybe Baby <3",
    ]

    return options


class Event:
    """
    The Event object represent an event and its poll

    Args:
        chat_id: id of the chat the event belongs to
        poll: initial telegram.Poll related to the event

    Attributes:
        chat_id: id of the chat the event belongs to
        poll: telegram.Poll object related to the event
        poll_id: id of the poll object
        poll_answers: dict of users and their answers to the poll
        status_message_id: id of the status message for the event
    """

    def __init__(self, chat_id: int, poll: Poll) -> None:
        self.chat_id = chat_id
        self.poll = poll

        self.poll_id = poll.id

        self.poll_answers: Dict[User, PollAnswer] = {}
        self.first_answer: User = None
        self.status_message_id = 0

    def __repr__(self) -> str:
        return str(self.__class__) + ": " + str(self.__dict__)

    @log.method
    def send_status_message(self, bot: Bot) -> None:
        """Send status message for the event poll"""
        chat_member_count = bot.get_chat_member_count(self.chat_id)
        status_message = bot.send_message(
            chat_id=self.chat_id,
            text=self._create_status_message(chat_member_count),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        self.status_message_id = status_message.message_id

    @log.method
    def update_status_message(self, bot: Bot) -> None:
        """Update status message for the event poll"""
        chat_member_count = bot.get_chat_member_count(self.chat_id)
        bot.edit_message_text(
            text=self._create_status_message(chat_member_count),
            chat_id=self.chat_id,
            message_id=self.status_message_id,
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    @log.method
    def _create_status_message(self, chat_member_count: int) -> str:
        """Create formatted status message for the event poll"""
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
                    message += f"\n  • {user.mention_markdown_v2()}"
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
        if self.first_answer is None:
            self.first_answer = poll_answer.user

        self.poll_answers[poll_answer.user] = poll_answer
        _logger.debug("%s", self)
