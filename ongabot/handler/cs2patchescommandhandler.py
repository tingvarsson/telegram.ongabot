"""This module contains the Cs2PatchesCommandHandler class."""

import logging
from typing import Optional, Set

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import CallbackContext, CommandHandler

from botdata import BotData
from cs2.patchnotesformat import render_patch_notes_html
from cs2.steamnews import get_client as get_steam_news_client
from utils.commands import CS2PATCHES
from utils.htmlblocks import send_html_with_fallback
from utils.log import log

_logger = logging.getLogger(__name__)


class Cs2PatchesCommandHandler(CommandHandler):
    """Handler for /cs2patches command"""

    def __init__(self) -> None:
        # Non-blocking: turning it on fetches from Steam, which can take up to ~20 s when Steam
        # is slow, and the application processes updates one at a time otherwise.
        super().__init__("cs2patches", callback, block=False)


async def _post_latest_patch_note(
    context: CallbackContext, chat_id: int, seen_at_subscribe: Optional[Set[str]]
) -> None:
    """Post the most recent CS2 patch note to one chat, so turning the feature on shows it.

    A one-off for this chat, never recorded in BotData.cs2_patchnotes_seen_gids. Whether to
    post is decided from that set as it was at the moment the chat subscribed: the sweep marks
    a patch seen and fixes its recipients in one step, so a patch already seen then will not
    reach this chat from the sweep, while one not yet seen will - posting it here as well
    would give the chat the same patch twice. Before the sweep has started tracking at all
    (None), it never announces what it finds, so the post is always this command's to make.
    """
    items = await get_steam_news_client().get_cs2_patch_notes()
    if not items:
        _logger.info("No CS2 patch note to post to chat_id=%s on subscribe (feed %s)", chat_id, items)
        return

    latest = max(items, key=lambda item: item.date)
    if seen_at_subscribe is not None and latest.gid not in seen_at_subscribe:
        _logger.info(
            "Latest CS2 patch note gid=%s not announced yet; the sweep will post it to chat_id=%s", latest.gid, chat_id
        )
        return

    try:
        for message in render_patch_notes_html([latest]):
            await send_html_with_fallback(context.bot, chat_id, message)
    except TelegramError as e:
        _logger.error("Failed to post latest CS2 patch note gid=%s to chat_id=%s: %s", latest.gid, chat_id, e)
        return
    _logger.info("Posted latest CS2 patch note gid=%s to chat_id=%s on subscribe", latest.gid, chat_id)


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Turn CS2 patch-note posts on or off for this chat, as result of /cs2patches"""
    if update.message is None or update.effective_chat is None:
        _logger.error("Received /cs2patches command without message or effective chat")
        return

    args = context.args or []
    if len(args) != 1 or args[0].lower() not in ("on", "off"):
        await update.message.reply_text(CS2PATCHES.usage)
        return

    chat_id = update.effective_chat.id
    bot_data: BotData = context.bot_data
    subscribed = bot_data.is_subscribed_to_cs2_patchnotes(chat_id)

    if args[0].lower() == "off":
        if not subscribed:
            await update.message.reply_text("CS2 patch notes are already off in this chat.")
            return
        bot_data.unsubscribe_from_cs2_patchnotes(chat_id)
        await update.message.reply_text("CS2 patch notes will no longer be posted in this chat.")
        return

    if subscribed:
        await update.message.reply_text("CS2 patch notes are already on in this chat.")
        return

    # Copied in the same synchronous step as subscribing, before any await - see
    # _post_latest_patch_note for why the decision must use the set as it was right now.
    seen = bot_data.cs2_patchnotes_seen_gids
    seen_at_subscribe = None if seen is None else set(seen)
    bot_data.subscribe_to_cs2_patchnotes(chat_id)
    await update.message.reply_text("CS2 patch notes will now be posted in this chat as Valve releases them.")
    await _post_latest_patch_note(context, chat_id, seen_at_subscribe)
