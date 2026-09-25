"""Answer a group's read commands in a private chat with the bot.

A command sent in a private chat has no group of its own. The group it reads is one the sender
is a member of right now, checked live with Telegram on every request. That check is also the
access control: nobody can read a group they are not in, or have left.
"""

import logging
from typing import List, Optional, Tuple

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatMemberStatus, ChatType
from telegram.error import TelegramError
from telegram.ext import CallbackContext

from botdata import BotData
from chat import Chat

_logger = logging.getLogger(__name__)

# Callback data of a group-picker button: dm_pick:<command>:<chat_id>[:<arg>]
DM_PICK_PREFIX = "dm_pick"

# Telegram rejects an inline button whose callback_data is longer than this.
CALLBACK_DATA_MAX_BYTES = 64

NOT_IN_ANY_GROUP = "You're not in any group I'm running in, so there is nothing to show you here."
PICK_GROUP_PROMPT = "Which group?"
GROUP_UNAVAILABLE = "That group isn't available to you any more."

_MEMBER_STATUSES = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}


def is_private_chat(update: Update) -> bool:
    """True when update comes from a private chat with the bot."""
    return update.effective_chat is not None and update.effective_chat.type == ChatType.PRIVATE


def private_commands_only(update: Update, context: CallbackContext) -> bool:
    """True when update's chat answers only the private commands: a private chat not authorized.

    A private chat a bot admin authorized answers every command, so its /help lists them all.
    """
    return is_private_chat(update) and not context.bot_data.is_authorized(update.effective_chat.id)


async def is_group_member(bot: Bot, chat_id: int, user_id: int) -> bool:
    """True when user_id is currently in the group chat_id, per Telegram."""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except TelegramError as e:
        # A group the bot was removed from, or one that migrated to a supergroup, ends up here.
        _logger.warning("Could not check user_id=%s in chat_id=%s: %s", user_id, chat_id, e)
        return False
    if member.status in _MEMBER_STATUSES:
        return True
    # A restricted user is still in the group, unless they left it while restricted.
    return member.status == ChatMemberStatus.RESTRICTED and bool(getattr(member, "is_member", False))


async def can_read_group(bot: Bot, bot_data: BotData, chat_id: int, user_id: int) -> bool:
    """True when user_id may read chat_id from a private chat: an authorized group they are in.

    Checked again on every button tap, because group membership and authorization can both
    change after a button was sent.
    """
    if chat_id >= 0 or not bot_data.is_authorized(chat_id):
        return False
    return await is_group_member(bot, chat_id, user_id)


async def member_group_ids(bot: Bot, bot_data: BotData, user_id: int) -> List[int]:
    """The authorized groups user_id is currently in, in a stable order."""
    # Group and supergroup ids are negative. A positive authorized id is a private chat a bot
    # admin authorized, which has no group data to read.
    group_ids = sorted(chat_id for chat_id in bot_data.authorized_chats if chat_id < 0)
    return [chat_id for chat_id in group_ids if await is_group_member(bot, chat_id, user_id)]


async def group_title(bot: Bot, chat_id: int) -> str:
    """The group's title, or its id when Telegram can't tell."""
    try:
        return (await bot.get_chat(chat_id)).title or str(chat_id)
    except TelegramError as e:
        _logger.warning("Could not fetch the title of chat_id=%s: %s", chat_id, e)
        return str(chat_id)


def encode_pick(command: str, chat_id: int, arg: str = "") -> str:
    """Callback data for the picker button that runs command against chat_id."""
    data = f"{DM_PICK_PREFIX}:{command}:{chat_id}"
    return f"{data}:{arg}" if arg else data


def decode_pick(data: str) -> Tuple[str, int, str]:
    """Split picker callback data into (command, chat_id, arg). Raises ValueError if malformed."""
    prefix, command, chat_id, *rest = data.split(":", 3)
    if prefix != DM_PICK_PREFIX or not command:
        raise ValueError(f"Not group-picker callback data: {data!r}")
    return command, int(chat_id), rest[0] if rest else ""


async def build_group_picker(bot: Bot, command: str, group_ids: List[int], arg: str = "") -> InlineKeyboardMarkup:
    """One button per group, labelled with its title, each running command against that group."""
    rows = [
        [InlineKeyboardButton(await group_title(bot, chat_id), callback_data=encode_pick(command, chat_id, arg))]
        for chat_id in group_ids
    ]
    return InlineKeyboardMarkup(rows)


async def resolve_group(update: Update, context: CallbackContext, command: str, arg: str = "") -> Optional[Chat]:
    """The group a read command is about, or None when there is nothing to answer yet.

    In a group that is the group itself. In a private chat it is the one group the sender is
    in; when there are several, this sends a group picker and returns None, and the picker's
    callback (DmGroupPickCallbackHandler) finishes the command. arg rides along on the picker
    buttons for commands that take one, so keep it short: the button data is capped at 64 bytes.
    """
    if not is_private_chat(update):
        return context.bot_data.get_chat(update.effective_chat.id)

    if update.effective_user is None:
        _logger.error("Received /%s in a private chat without an effective user", command)
        return None

    user_id = update.effective_user.id
    group_ids = await member_group_ids(context.bot, context.bot_data, user_id)
    _logger.info("/%s in a private chat from user_id=%s, member of chat_ids=%s", command, user_id, group_ids)

    if not group_ids:
        await update.message.reply_text(NOT_IN_ANY_GROUP)
        return None

    if len(group_ids) == 1:
        return context.bot_data.get_chat(group_ids[0])

    keyboard = await build_group_picker(context.bot, command, group_ids, arg)
    await update.message.reply_text(PICK_GROUP_PROMPT, reply_markup=keyboard)
    return None
