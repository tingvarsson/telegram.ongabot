"""This module contains the ChangelogCommandHandler class."""

import logging

from telegram import LinkPreviewOptions, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import CallbackContext, CommandHandler

from _version import __version__
from utils.changelog import get_changelog
from utils.changelogformat import render_changelog_html, to_plain_text
from utils.commands import CHANGELOG
from utils.log import log

_logger = logging.getLogger(__name__)

# The changelog is full of GitHub compare links; a preview per message is exactly the noise
# collapsing the body is meant to remove.
_NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


@log
async def callback(update: Update, context: CallbackContext) -> None:
    """Reply with the last N changelog entries (default 1) as seen from this build."""
    count = 1
    if context.args:
        arg = context.args[0]
        if not arg.isdigit() or int(arg) < 1:
            await update.message.reply_text(CHANGELOG.usage)
            return
        count = int(arg)
    entry = get_changelog(__version__, count)
    # Each release renders to a visible header plus a collapsed body. Several entries
    # together exceed Telegram's message limit, which would fail the whole reply rather
    # than truncate it - the renderer splits them into messages that each fit.
    messages = render_changelog_html(entry)
    _logger.info("Replying with %d changelog entr(ies) in %d message(s)", count, len(messages))
    for message in messages:
        try:
            await update.message.reply_text(message, parse_mode=ParseMode.HTML, link_preview_options=_NO_PREVIEW)
        except BadRequest as e:
            # A malformed entity fails the whole message; resend it unformatted rather than
            # leaving the user with nothing.
            _logger.warning("Changelog message rejected as HTML (%s); resending as plain text", e)
            await update.message.reply_text(to_plain_text(message), link_preview_options=_NO_PREVIEW)


class ChangelogCommandHandler(CommandHandler):
    """Handler for /changelog command."""

    def __init__(self) -> None:
        super().__init__("changelog", callback)
