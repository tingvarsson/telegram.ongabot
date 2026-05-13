#!/usr/bin/env python3
"""An application that runs a telegram bot called ONGAbot"""

import datetime
import logging
import os

from telegram.ext import Application, CallbackContext, ContextTypes, PicklePersistence
from telegram.error import TelegramError

import eventcreator
from botdata import BotData
from handler import AuthorizationHandler
from handler import AuthorizeCommandHandler
from handler import CancelEventCommandHandler
from handler import DeAuthorizeCommandHandler
from handler import DeScheduleCommandHandler
from handler import EventPollAnswerHandler
from handler import EventPollHandler
from handler import HelpCommandHandler
from handler import NewEventCommandHandler
from handler import OngaCommandHandler
from handler import RescheduleCommandHandler
from handler import ScheduleCommandHandler
from handler import StartCommandHandler
from handler import UpdateEventCommandHandler
from userdata import UserData
from utils import log

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@log.log
async def complete_past_events_callback(context: CallbackContext) -> None:
    """Auto-complete any events whose date has passed: mark complete, update status, unpin poll."""
    bot_data: BotData = context.bot_data
    today = datetime.date.today()

    # Iterate through all chats and their events to find and complete past events
    for chat in bot_data.chats.values():
        for event in list(chat.events.values()):
            if not event.completed and event.event_date < today:
                event.mark_complete()
                try:
                    await event.update_status_message(context.bot)
                except TelegramError as exc:
                    logger.error(
                        "Failed to update status message for poll_id=%s: %s",
                        event.poll_id,
                        exc,
                    )
                await chat.remove_pinned_poll(event.poll_id)
                logger.info(
                    "Auto-completed past event poll_id=%s (date=%s) in chat_id=%s",
                    event.poll_id,
                    event.event_date,
                    chat.chat_id,
                )


async def post_init(application: Application) -> None:
    """Called after the application initializes with persistence loaded."""
    bot_data: BotData = application.bot_data

    # Seed authorized chats from env var (idempotent; safe to keep in .env)
    for raw_id in os.getenv("AUTHORIZED_CHAT_IDS", "").split(","):
        if raw_id.strip().lstrip("-").isdigit():
            bot_data.authorize_chat(int(raw_id.strip()))

    if application.job_queue is None:
        logger.error("Job queue is not available in post_init. Event cleanup jobs will not be scheduled.")
        return

    bot_data.schedule_all_event_jobs(application.job_queue, eventcreator.create_event_callback)

    # Schedule daily cleanup of past events
    application.job_queue.run_once(complete_past_events_callback, when=5, name="complete_past_events_startup")
    application.job_queue.run_daily(
        complete_past_events_callback, time=datetime.time(0, 0, 0), name="complete_past_events"
    )


async def error(update: object, context: CallbackContext) -> None:
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def main() -> None:
    """Setup and run ONGAbot"""
    context_types = ContextTypes(bot_data=BotData, user_data=UserData)

    persistence = PicklePersistence(filepath=os.getenv("DB_PATH", "ongabot.db"), context_types=context_types)

    api_token = os.getenv("API_TOKEN")
    if not api_token:
        logger.error("API_TOKEN environment variable is not set. Exiting.")
        return

    application = (
        Application.builder()
        .token(api_token)
        .persistence(persistence)
        .context_types(context_types)
        .post_init(post_init)
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
    application.add_handler(UpdateEventCommandHandler())
    application.add_handler(RescheduleCommandHandler())
    application.add_error_handler(error)

    # Start the bot
    application.run_polling()


if __name__ == "__main__":
    main()
