"""This module contains the ShrinkCommandHandler class."""

import logging
from typing import Optional, Sequence, Tuple

from telegram import Message, Update, User
from telegram.constants import MessageEntityType
from telegram.ext import CallbackContext, CommandHandler

from chat import Chat
from shrink import render_shrink_message
from utils.commands import SHRINK
from utils.dm import is_private_chat, resolve_group
from utils.log import log

_logger = logging.getLogger(__name__)


class ShrinkCommandHandler(CommandHandler):
    """Handler for /shrink command."""

    def __init__(self) -> None:
        super().__init__("shrink", callback)


async def send_shrink(message: Message, chat: Chat, user: Optional[User], username: Optional[str] = None) -> None:
    """Reply to message with the session note for user, or for username when given instead."""
    await message.reply_text(render_shrink_message(chat, user=user, username=username))


def _replied_to_user(message: Message) -> Optional[User]:
    """The sender of the message /shrink replies to, if it is a real reply.

    In a forum topic every message carries the topic's creation message as reply_to_message,
    so that one does not count as replying to anyone.
    """
    reply = message.reply_to_message
    if reply is None or reply.forum_topic_created is not None:
        return None
    return reply.from_user


def _parse_username(args: Sequence[str]) -> Optional[str]:
    """The username in /shrink @username, without the @. Raises ValueError on any other args."""
    if not args:
        return None
    if len(args) > 1 or not args[0].startswith("@") or len(args[0]) < 2:
        raise ValueError(f"Not a single @username: {args!r}")
    return args[0][1:]


def _text_mention(message: Message) -> Optional[User]:
    """The user of a text mention in message, if any.

    Picking someone without a username from the @ autocomplete inserts their plain name as a
    text mention rather than an @username, and the mention itself carries the user.
    """
    for entity in message.entities or ():
        if entity.type == MessageEntityType.TEXT_MENTION and entity.user is not None:
            return entity.user
    return None


def _patient(update: Update, context: CallbackContext) -> Tuple[Optional[User], Optional[str]]:
    """(user, username) to diagnose; exactly one is set. Raises ValueError on bad args.

    In a private chat the patient is always the sender, since there is nobody else to reply to,
    so any args there are rejected rather than silently ignored. In a group a mention wins over
    a reply, which wins over the sender.
    """
    if is_private_chat(update):
        if context.args:
            raise ValueError(f"Args in a private chat, where /shrink always diagnoses the sender: {context.args!r}")
        return update.effective_user, None
    mentioned = _text_mention(update.message)
    if mentioned is not None:
        return mentioned, None
    username = _parse_username(context.args or [])
    if username is not None:
        return None, username
    return _replied_to_user(update.message) or update.effective_user, None


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Reply with a mock diagnosis from someone's voting history, as result of /shrink"""
    if update.message is None or update.effective_chat is None:
        _logger.error("Received /shrink command without message or effective chat")
        return

    try:
        user, username = _patient(update, context)
    except ValueError as e:
        _logger.info("Rejected /shrink in chat_id=%s: %s", update.effective_chat.id, e)
        await update.message.reply_text(SHRINK.usage)
        return
    if username is not None:
        patient = f"@{username}"
    elif user is not None:
        patient = f"user_id={user.id}"
    else:
        _logger.error("Received /shrink in chat_id=%s without an effective user", update.effective_chat.id)
        return

    chat = await resolve_group(update, context, SHRINK.command)
    if chat is None:
        return

    asker = update.effective_user.id if update.effective_user else None
    _logger.info("/shrink from user_id=%s on %s in chat_id=%s", asker, patient, chat.chat_id)
    await send_shrink(update.message, chat, user, username)
