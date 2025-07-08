"""This module contains the Event class."""

import logging
from typing import Dict


from telegram import Bot, Poll, PollAnswer, User
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown

from utils import log


_logger = logging.getLogger(__name__)


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
    def _create_status_message_text(self, chat_member_count: int) -> str:
        """Create formatted status message text for the event poll"""
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
