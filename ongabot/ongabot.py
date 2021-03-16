#!/usr/bin/env python3
"""An application that runs a telegram bot called ONGAbot"""

import logging
import os

from telegram.ext import CallbackContext, PicklePersistence, Updater

from handler import EventPollAnswerHandler
from handler import EventPollHandler
from handler import HelpCommandHandler
from handler import NewEventCommandHandler
from handler import CancelEventCommandHandler
from handler import OngaCommandHandler
from handler import StartCommandHandler


logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def error(update: object, context: CallbackContext) -> None:
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def main() -> None:
    """Setup and run ONGAbot"""
    persistence = PicklePersistence(filename=os.getenv("DB_PATH", "ongabot.db"))

    updater = Updater(os.getenv("API_TOKEN"), persistence=persistence, use_context=True)

    # Register handlers
    dispatcher = updater.dispatcher
    dispatcher.add_handler(StartCommandHandler())
    dispatcher.add_handler(HelpCommandHandler())
    dispatcher.add_handler(OngaCommandHandler())
    dispatcher.add_handler(NewEventCommandHandler())
    dispatcher.add_handler(CancelEventCommandHandler())
    dispatcher.add_handler(EventPollHandler())
    dispatcher.add_handler(EventPollAnswerHandler())
    dispatcher.add_error_handler(error)

    # Start the bot
    updater.start_polling()

    # Block until you press Ctrl-C or the process receives SIGINT, SIGTERM or
    # SIGABRT. This should be used most of the time, since start_polling() is
    # non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == "__main__":
    main()
