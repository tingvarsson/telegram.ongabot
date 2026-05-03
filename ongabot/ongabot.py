#!/usr/bin/env python3
"""An application that runs a telegram bot called ONGAbot"""

import asyncio
import logging
import os

from telegram.ext import Application, CallbackContext, ContextTypes, PicklePersistence

from botdata import BotData
from eventcreator import create_event_callback
from handler import AuthorizationHandler
from handler import AuthorizeCommandHandler
from handler import DeAuthorizeCommandHandler
from handler import EventPollAnswerHandler
from handler import EventPollHandler
from handler import HelpCommandHandler
from handler import NewEventCommandHandler
from handler import CancelEventCommandHandler
from handler import OngaCommandHandler
from handler import StartCommandHandler
from handler import ScheduleCommandHandler
from handler import DeScheduleCommandHandler
from userdata import UserData

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def error(update: object, context: CallbackContext) -> None:
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def main() -> None:
    """Setup and run ONGAbot"""
    context_types = ContextTypes(bot_data=BotData, user_data=UserData)

    persistence = PicklePersistence(
        filepath=os.getenv("DB_PATH", "ongabot.db"), context_types=context_types
    )

    application = (
        Application.builder()
        .token(os.getenv("API_TOKEN"))
        .persistence(persistence)
        .context_types(context_types)
        .build()
    )

    # Authorization gate — runs before all other handlers (group -1)
    application.add_handler(AuthorizationHandler(), group=-1)

    # Register handlers
    application.add_handler(AuthorizeCommandHandler())
    application.add_handler(DeAuthorizeCommandHandler())
    application.add_handler(StartCommandHandler())
    application.add_handler(HelpCommandHandler())
    application.add_handler(OngaCommandHandler())
    application.add_handler(NewEventCommandHandler())
    application.add_handler(CancelEventCommandHandler())
    application.add_handler(EventPollHandler())
    application.add_handler(EventPollAnswerHandler())
    application.add_handler(ScheduleCommandHandler())
    application.add_handler(DeScheduleCommandHandler())
    application.add_error_handler(error)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bot_data: BotData = loop.run_until_complete(persistence.get_bot_data())
    if bot_data:
        bot_data.schedule_all_event_jobs(application.job_queue, create_event_callback)
        # Seed authorized chats from env var (idempotent; safe to keep in .env)
        for raw_id in os.getenv("AUTHORIZED_CHAT_IDS", "").split(","):
            if raw_id.strip().lstrip("-").isdigit():
                bot_data.authorize_chat(int(raw_id.strip()))

    # Start the bot
    application.run_polling()


if __name__ == "__main__":
    main()
