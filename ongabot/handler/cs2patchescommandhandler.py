"""This module contains the Cs2PatchesCommandHandler class."""

import logging

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
        super().__init__("cs2patches", callback)


async def _post_latest_patch_note(context: CallbackContext, bot_data: BotData, chat_id: int) -> None:
    """Post the most recent CS2 patch note to one chat, so turning the feature on shows it.

    A one-off for this chat only, never recorded in BotData.cs2_patchnotes_seen_gids - that
    set drives the sweep job's broadcast to every subscriber. It is read, though: a patch the
    sweep has not announced yet is left to the sweep, which now includes this chat and would
    otherwise post it here a second time.
    """
    items = await get_steam_news_client().get_cs2_patch_notes()
    if not items:
        _logger.info("No CS2 patch note to post to chat_id=%s on subscribe (feed %s)", chat_id, items)
        return

    latest = max(items, key=lambda item: item.date)
    seen = bot_data.cs2_patchnotes_seen_gids
    if seen is not None and latest.gid not in seen:
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
    if args[0].lower() == "off":
        bot_data.unsubscribe_from_cs2_patchnotes(chat_id)
        await update.message.reply_text("CS2 patch notes will no longer be posted in this chat.")
        return

    bot_data.subscribe_to_cs2_patchnotes(chat_id)
    await update.message.reply_text("CS2 patch notes will now be posted in this chat as Valve releases them.")
    await _post_latest_patch_note(context, bot_data, chat_id)
