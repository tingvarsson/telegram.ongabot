"""This module contains the UnverifyCommandHandler and VerifyCommandHandler classes."""

import logging
from typing import Optional

from telegram import Message, MessageEntity, Update, User
from telegram.constants import ChatType
from telegram.error import TelegramError
from telegram.ext import CallbackContext, CommandHandler

from chat import Chat
from utils.commands import UNVERIFY, VERIFY, CommandInfo
from utils.log import log
from verification import BADGE, start_vote

_logger = logging.getLogger(__name__)


class UnverifyCommandHandler(CommandHandler):
    """Handler for /unverify command"""

    def __init__(self) -> None:
        super().__init__("unverify", unverify_callback)


class VerifyCommandHandler(CommandHandler):
    """Handler for /verify command"""

    def __init__(self) -> None:
        super().__init__("verify", verify_callback)


def resolve_target(message: Message, chat: Chat) -> Optional[User]:
    """Find the member a /unverify or /verify is about.

    In order: the author of the replied-to message, a text mention (a member without a
    username, picked from the mention list), or an @username of someone who has voted on one
    of this chat's events (see Chat.find_user_by_username).
    """
    reply = message.reply_to_message
    # In a forum topic every message "replies" to the topic's creation message; that is not
    # the member the command is about.
    if reply is not None and reply.from_user is not None and reply.forum_topic_created is None:
        return reply.from_user

    for entity, text in message.parse_entities([MessageEntity.TEXT_MENTION, MessageEntity.MENTION]).items():
        if entity.type == MessageEntity.TEXT_MENTION and entity.user is not None:
            return entity.user
        if entity.type == MessageEntity.MENTION:
            user = chat.find_user_by_username(text)
            if user is not None:
                return user
            _logger.info("No known member with username=%s in chat_id=%s", text, chat.chat_id)
    return None


async def _handle(update: Update, context: CallbackContext, info: CommandInfo, unverify: bool) -> None:
    """Start a vote to unverify (or verify again) a member, after checking it makes sense."""
    if update.message is None or update.effective_chat is None:
        _logger.error("Received /%s command without message or effective chat", info.command)
        return
    message = update.message
    if update.effective_chat.type == ChatType.PRIVATE:
        # The authorization gate already keeps group commands out of private chats; belt and braces.
        await message.reply_text(f"/{info.command} only works in a group chat.")
        return

    chat: Chat = context.bot_data.get_chat(update.effective_chat.id)
    target = resolve_target(message, chat)
    if target is None:
        await message.reply_text(info.usage)
        return

    name = target.first_name
    refusal = None
    if target.is_bot:
        refusal = "Nice try. Bots are born verified."
    elif unverify and chat.is_unverified(target.id):
        refusal = f"{name} is already unverified {BADGE}"
    elif not unverify and not chat.is_unverified(target.id):
        refusal = f"{name} is already verified. Suspiciously so."
    elif chat.open_vote_for(target.id) is not None:
        refusal = f"There is already a vote on {name}. Go vote!"
    if refusal is not None:
        _logger.info("Refused /%s on user_id=%s in chat_id=%s: %s", info.command, target.id, chat.chat_id, refusal)
        await message.reply_text(refusal)
        return

    if context.job_queue is None:
        _logger.error("No job queue: cannot close a /%s vote, so none is started", info.command)
        return
    try:
        await start_vote(context.bot, context.job_queue, chat, target.id, name, unverify)
    except TelegramError as e:
        _logger.error(
            "Failed to start /%s vote on user_id=%s in chat_id=%s: %s", info.command, target.id, chat.chat_id, e
        )


@log
async def unverify_callback(update: Update, context: CallbackContext) -> None:
    """Start a group vote to unverify a member, as result of /unverify"""
    await _handle(update, context, UNVERIFY, unverify=True)


@log
async def verify_callback(update: Update, context: CallbackContext) -> None:
    """Start a group vote to verify a member again, as result of /verify"""
    await _handle(update, context, VERIFY, unverify=False)
