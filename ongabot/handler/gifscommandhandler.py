"""This module contains the GifsCommandHandler class."""

import logging

from telegram import Update
from telegram.ext import CallbackContext, CommandHandler

from chat import Chat
from gifs.client import get_client
from utils.commands import GIFS
from utils.log import log

_logger = logging.getLogger(__name__)

# Giphy's terms ask for attribution wherever its GIFs are shown, and this is the bot's one
# message about them.
ATTRIBUTION = "Powered by GIPHY"
# Said where GIFs are on but the bot has no GIPHY_API_KEY, so nobody waits for one in vain.
NO_KEY_NOTE = "This bot has no Giphy key yet, so for now the moments go out as plain text."


class GifsCommandHandler(CommandHandler):
    """Handler for /gifs command"""

    def __init__(self) -> None:
        super().__init__("gifs", callback=callback)


def _state(chat: Chat) -> str:
    return "on" if chat.gifs_enabled else "off"


def _footer(chat: Chat) -> str:
    """The attribution, or what stands in the way of any GIF, for a reply about GIFs being on."""
    if chat.gifs_enabled and not get_client().has_key:
        return NO_KEY_NOTE
    return ATTRIBUTION


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Show or switch the GIFs at the bot's big moments, as result of /gifs [on|off]"""
    if update.message is None or update.effective_chat is None:
        _logger.error("Received /gifs command without message or effective chat")
        return

    chat: Chat = context.bot_data.get_chat(update.effective_chat.id)
    args = context.args or []

    if not args:
        await update.message.reply_text(
            f"GIFs are {_state(chat)} in this chat. Switch them with /gifs on or /gifs off.\n{_footer(chat)}"
        )
        return
    if len(args) != 1 or args[0].lower() not in ("on", "off"):
        await update.message.reply_text(GIFS.usage)
        return

    enabled = args[0].lower() == "on"
    if chat.gifs_enabled == enabled:
        await update.message.reply_text(f"GIFs are already {_state(chat)} in this chat.")
        return

    chat.gifs_enabled = enabled
    _logger.info("GIFs for chat_id=%s turned %s", chat.chat_id, _state(chat))
    if enabled:
        await update.message.reply_text(f"GIFs are on: the bot's big moments now come with one.\n{_footer(chat)}")
    else:
        await update.message.reply_text("GIFs are off: the bot's big moments go out as plain text.")
