#!/usr/bin/env python3
"""An application that runs a telegram bot called ONGAbot"""

import datetime
import logging
import os
from typing import Any, Dict, cast

from telegram import Bot, BotCommand, LinkPreviewOptions
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackContext, ContextTypes, JobQueue, PicklePersistence
from telegram.error import TelegramError

import eventcreator
from _version import __version__ as CURRENT_VERSION
from botdata import BotData
from cs2.leetify import get_client
from cs2.report import event_results
from handler import AuthorizationHandler
from handler import AuthorizeCommandHandler
from handler import CancelEventCommandHandler
from handler import ChangelogCommandHandler
from handler import Cs2CommandHandler
from handler import DeAuthorizeCommandHandler
from handler import DeScheduleCommandHandler
from handler import EventPollAnswerHandler
from handler import EventPollHandler
from handler import HelpCommandHandler
from handler import LeaderboardCommandHandler
from handler import LinkSteamCommandHandler
from handler import NewEventCommandHandler
from handler import OngaCommandHandler
from handler import RescheduleCommandHandler
from handler import ScheduleCommandHandler
from handler import StartCommandHandler
from handler import StatisticsCommandHandler
from handler import StatisticsSortCallbackHandler
from handler import UnLinkSteamCommandHandler
from handler import UpdateEventCommandHandler
from userdata import UserData
from utils import log
from utils.changelog import get_changelog_delta, is_dev_version
from utils.commands import ALL_COMMANDS, BOT_DESCRIPTION, BOT_SHORT_DESCRIPTION
from utils.points import render_event_recap_message

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Leetify only has a match once its demo has been processed, which is typically well after
# the midnight recap. The sweep therefore starts shortly after an event completes and keeps
# checking until the night's match list stops growing.
CS2_SWEEP_FIRST = datetime.timedelta(minutes=30)
CS2_SWEEP_INTERVAL = datetime.timedelta(minutes=20)
# Long enough to cover a late night plus slow demo processing; after this the sweep posts
# whatever it found and stops, so a job never lives forever.
CS2_SWEEP_GIVE_UP = datetime.timedelta(hours=14)


def schedule_cs2_sweep(job_queue: JobQueue, chat_id: int, event_date: datetime.date) -> None:
    """Start the repeating job that posts CS2 results for a just-completed event."""
    if job_queue is None:
        logger.error("No job queue available; CS2 results for %s will not be posted", event_date)
        return

    job_queue.run_repeating(
        cs2_sweep_callback,
        interval=CS2_SWEEP_INTERVAL,
        first=CS2_SWEEP_FIRST,
        name=f"cs2_sweep_{chat_id}_{event_date}",
        chat_id=chat_id,
        data={
            "event_date": event_date,
            # Match ids seen on the previous pass. Transient job state, never persisted -
            # two identical passes in a row mean the night has settled.
            "seen": set(),
            "deadline": datetime.datetime.now() + CS2_SWEEP_GIVE_UP,
        },
    )
    logger.info("Scheduled CS2 results sweep for chat_id=%s event_date=%s", chat_id, event_date)


@log.log
async def cs2_sweep_callback(context: CallbackContext) -> None:
    """Post the CS2 results for one event, once the night's match list has settled.

    Runs repeatedly and removes itself as soon as it has posted, or once the deadline passes.
    """
    job = context.job
    bot_data: BotData = context.bot_data
    chat = bot_data.get_chat(job.chat_id)
    # Job.data is typed as object by python-telegram-bot; this job always sets the dict
    # schedule_cs2_sweep builds.
    data = cast(Dict[str, Any], job.data)
    event_date = data["event_date"]

    event = chat.get_event_by_date(event_date)
    if event is None or event.cs2_reported:
        logger.debug("Nothing left to sweep for chat_id=%s on %s", job.chat_id, event_date)
        job.schedule_removal()
        return

    expired = datetime.datetime.now() >= data["deadline"]
    session, text = await event_results(get_client(), chat, event, context.application.user_data)

    if session is None:
        # Leetify unreachable - retry on the next pass rather than claim nobody played.
        if expired:
            logger.warning(
                "Giving up on CS2 results for chat_id=%s on %s: Leetify unreachable", job.chat_id, event_date
            )
            job.schedule_removal()
        return

    match_ids = {match.id for match in session.matches}
    settled = bool(match_ids) and match_ids == data["seen"]
    data["seen"] = match_ids

    if not settled and not (expired and match_ids):
        if expired:
            logger.info("No CS2 matches found for chat_id=%s on %s; giving up", job.chat_id, event_date)
            job.schedule_removal()
        else:
            logger.debug("CS2 sweep for %s still settling: %d match(es) so far", event_date, len(match_ids))
        return

    try:
        await context.bot.send_message(
            chat.chat_id,
            text,
            parse_mode=ParseMode.MARKDOWN_V2,
            # The per-match Leetify links would otherwise each drag in a preview card.
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    except TelegramError as e:
        # Leave the event unreported and the job alive, so the next pass can try again.
        logger.warning("Failed to send CS2 results for chat_id=%s on %s: %s", job.chat_id, event_date, e)
        return

    event.record_cs2_session(session.played_user_ids)
    job.schedule_removal()
    logger.info(
        "Posted CS2 results for chat_id=%s on %s: %d match(es)",
        job.chat_id,
        event_date,
        len(session.matches),
    )


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
                except TelegramError as e:
                    logger.error(
                        "Failed to update status message for chat_id=%s poll_id=%s: %s",
                        chat.chat_id,
                        event.poll_id,
                        e,
                    )
                try:
                    await chat.remove_pinned_poll(event.poll_id)
                except TelegramError as e:
                    logger.error(
                        "Failed to remove pinned poll for chat_id=%s poll_id=%s: %s",
                        chat.chat_id,
                        event.poll_id,
                        e,
                    )
                # Banger Points recap. The event is already marked complete, so a failure here
                # is never retried on the next sweep - log it loudly rather than silently
                # dropping the update. Cancelled events are skipped: /cancelevent completes
                # them too, and they are excluded from scoring entirely.
                if not event.cancelled:
                    try:
                        await context.bot.send_message(
                            chat.chat_id,
                            render_event_recap_message(chat, event),
                            parse_mode=ParseMode.MARKDOWN_V2,
                        )
                    except TelegramError as e:
                        logger.warning(
                            "Failed to send Banger Points recap for chat_id=%s poll_id=%s: %s",
                            chat.chat_id,
                            event.poll_id,
                            e,
                        )
                    # CS2 results follow separately: Leetify has not processed the night's
                    # demos yet at the moment this recap goes out.
                    schedule_cs2_sweep(context.job_queue, chat.chat_id, event.event_date)
                logger.info(
                    "Auto-completed past event poll_id=%s (date=%s) in chat_id=%s",
                    event.poll_id,
                    event.event_date,
                    chat.chat_id,
                )


async def setup_bot_metadata(bot: Bot) -> None:
    """Register command menu, description, and short description with Telegram."""
    commands = [BotCommand(cmd.command, cmd.menu_description) for cmd in ALL_COMMANDS]
    try:
        await bot.set_my_commands(commands)
        logger.info("Bot commands registered (%d commands)", len(commands))
    except TelegramError as e:
        logger.error("Failed to set bot commands: %s", e)
    try:
        await bot.set_my_description(BOT_DESCRIPTION)
        logger.info("Bot description registered")
    except TelegramError as e:
        logger.error("Failed to set bot description: %s", e)
    try:
        await bot.set_my_short_description(BOT_SHORT_DESCRIPTION)
        logger.info("Bot short description registered")
    except TelegramError as e:
        logger.error("Failed to set bot short description: %s", e)


async def _announce_new_version(bot: Bot, bot_data: BotData, old_version: str, new_version: str) -> None:
    """Send a version-change announcement to all authorized chats."""
    delta = get_changelog_delta(old_version, new_version)
    text = f"ONGAbot updated to v{new_version}!\n\n{delta}"
    # Truncate to Telegram's 4096-character message limit
    if len(text) > 4096:
        text = text[:4090] + "\n..."
    for chat_id in bot_data.authorized_chats:
        try:
            await bot.send_message(chat_id=chat_id, text=text)
            logger.info("Sent version announcement to chat_id=%s", chat_id)
        except TelegramError as e:
            logger.error("Failed to send version announcement to chat_id=%s: %s", chat_id, e)


async def post_init(application: Application) -> None:
    """Called after the application initializes with persistence loaded."""
    bot_data: BotData = application.bot_data

    # Seed authorized chats from env var (idempotent; safe to keep in .env)
    for raw_id in os.getenv("AUTHORIZED_CHAT_IDS", "").split(","):
        if raw_id.strip().lstrip("-").isdigit():
            bot_data.authorize_chat(int(raw_id.strip()))

    await setup_bot_metadata(application.bot)

    stored_version = bot_data.last_known_version
    if is_dev_version(CURRENT_VERSION):
        # Development build: never announce and never overwrite the last known
        # release, so the next real release still announces the full delta.
        logger.info("Development build %s — skipping version announcement", CURRENT_VERSION)
    elif stored_version is None:
        # First startup after version tracking was introduced; record silently
        logger.info("Initializing version tracking at %s", CURRENT_VERSION)
        bot_data.last_known_version = CURRENT_VERSION
    elif stored_version != CURRENT_VERSION:
        logger.info("Version change detected: %s → %s", stored_version, CURRENT_VERSION)
        await _announce_new_version(application.bot, bot_data, stored_version, CURRENT_VERSION)
        bot_data.last_known_version = CURRENT_VERSION

    if application.job_queue is None:
        logger.error("Job queue is not available in post_init. Event cleanup jobs will not be scheduled.")
        return

    try:
        bot_data.schedule_all_event_jobs(application.job_queue, eventcreator.create_event_callback)
    except Exception as e:  # pylint: disable=broad-except
        logger.error(
            "Failed to restore event jobs from persisted data — recurring polls will not fire: %s",
            e,
        )

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
    application.add_handler(ChangelogCommandHandler())
    application.add_handler(OngaCommandHandler())
    application.add_handler(NewEventCommandHandler())
    application.add_handler(CancelEventCommandHandler())
    application.add_handler(EventPollHandler())
    application.add_handler(EventPollAnswerHandler())
    application.add_handler(ScheduleCommandHandler())
    application.add_handler(DeScheduleCommandHandler())
    application.add_handler(UpdateEventCommandHandler())
    application.add_handler(RescheduleCommandHandler())
    application.add_handler(StatisticsCommandHandler())
    application.add_handler(StatisticsSortCallbackHandler())
    application.add_handler(LeaderboardCommandHandler())
    application.add_handler(Cs2CommandHandler())
    application.add_handler(LinkSteamCommandHandler())
    application.add_handler(UnLinkSteamCommandHandler())
    application.add_error_handler(error)

    # Start the bot
    application.run_polling()


if __name__ == "__main__":
    main()
