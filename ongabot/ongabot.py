#!/usr/bin/env python3
"""An application that runs a telegram bot called ONGAbot"""

import datetime
import logging
import os
from typing import Any, Dict, cast

from telegram import Bot, BotCommand, LinkPreviewOptions
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackContext, ContextTypes, JobQueue, PicklePersistence
from telegram.error import BadRequest, TelegramError

import eventcreator
from _version import __version__ as CURRENT_VERSION
from botdata import BotData
from cs2.leetify import get_client
from cs2.report import event_session, render_results
from event import Event
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
from utils.changelog import get_changelog_delta, is_dev_version, split_for_telegram
from utils.commands import ALL_COMMANDS, BOT_DESCRIPTION, BOT_SHORT_DESCRIPTION
from utils.points import render_event_recap_message

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# The sweep runs alongside the night itself: it starts when the gaming starts and picks up
# each match a little after it ends, once Leetify has processed its demo. Results are posted
# as one message that is edited as the night goes on, rather than a single post the morning
# after.
CS2_SWEEP_INTERVAL = datetime.timedelta(minutes=20)
# How long the match list must stay unchanged before the night counts as over. A match runs
# ~45 min and the gap to the next one is rarely more than an hour, so this comfortably spans
# a break between matches without waiting out the full deadline.
CS2_SWEEP_SETTLE = datetime.timedelta(minutes=90)
# Measured from the event's start time, so a sweep started at 18:30 gives up at 08:30. Long
# enough to cover a late night plus slow demo processing; a job never lives forever.
CS2_SWEEP_GIVE_UP = datetime.timedelta(hours=14)


def cs2_sweep_job_name(chat_id: int, event_date: datetime.date) -> str:
    """Name of the sweep job for one chat's event. Also the guard against scheduling twice."""
    return f"cs2_sweep_{chat_id}_{event_date}"


def schedule_cs2_sweep(
    job_queue: JobQueue,
    chat_id: int,
    event_date: datetime.date,
    start_time: datetime.time,
) -> None:
    """Start the repeating job that posts and updates CS2 results for one event.

    The first pass runs at the event's start time, or immediately if that has already passed -
    which is what makes the job resumable after a restart mid-evening.
    """
    if job_queue is None:
        logger.error("No job queue available; CS2 results for %s will not be posted", event_date)
        return

    name = cs2_sweep_job_name(chat_id, event_date)
    # The hourly scheduler and the event-completion fallback both reach this for the same
    # event; whichever gets there first owns the sweep.
    if job_queue.get_jobs_by_name(name):
        logger.debug("CS2 sweep %s is already scheduled", name)
        return

    now = datetime.datetime.now()
    starts_at = datetime.datetime.combine(event_date, start_time)
    job_queue.run_repeating(
        cs2_sweep_callback,
        interval=CS2_SWEEP_INTERVAL,
        first=max(now, starts_at),
        name=name,
        chat_id=chat_id,
        data={
            "event_date": event_date,
            # Match ids seen on the previous pass, and when that set last changed. Transient
            # job state, never persisted - a long enough quiet spell means the night is over.
            "seen": set(),
            "quiet_since": now,
            "deadline": starts_at + CS2_SWEEP_GIVE_UP,
        },
    )
    logger.info(
        "Scheduled CS2 results sweep for chat_id=%s event_date=%s starting %s",
        chat_id,
        event_date,
        max(now, starts_at),
    )


@log.log
async def schedule_todays_cs2_sweeps_callback(context: CallbackContext) -> None:
    """Start a CS2 sweep for every chat with an event today.

    Runs hourly, and scheduling is idempotent, so this covers an event created on its own day
    as well as the daily rollover. Jobs are not persisted - PicklePersistence stores bot_data,
    not the JobQueue - so the pass right after startup is also what resumes a sweep that a
    restart killed halfway through the evening.
    """
    bot_data: BotData = context.bot_data
    today = datetime.date.today()

    for chat in bot_data.chats.values():
        event = chat.get_event_by_date(today)
        if event is None or event.cancelled or event.cs2_reported:
            continue
        schedule_cs2_sweep(context.job_queue, chat.chat_id, today, event.start_time)


async def _publish_cs2_results(context: CallbackContext, event: Event, text: str) -> int:
    """Send the CS2 results message, or edit the one this event already has.

    Returns the message id it wrote to. Raises TelegramError so the caller can decide whether
    to retry; a message that has been deleted from the chat resets the event to "not posted"
    and is then sent afresh.
    """
    send_args = {
        "parse_mode": ParseMode.MARKDOWN_V2,
        # The per-match Leetify links would otherwise each drag in a preview card.
        "link_preview_options": LinkPreviewOptions(is_disabled=True),
    }

    if event.cs2_message_id:
        try:
            await context.bot.edit_message_text(
                text,
                chat_id=event.chat_id,
                message_id=event.cs2_message_id,
                **send_args,
            )
            return event.cs2_message_id
        except BadRequest as e:
            # "Message to edit not found" - somebody deleted it. Anything else (bad markup,
            # message too long) would fail on a fresh send too, so let it propagate.
            if "not found" not in str(e).lower():
                raise
            logger.warning(
                "CS2 results message %s is gone from chat_id=%s; posting a new one",
                event.cs2_message_id,
                event.chat_id,
            )
            event.cs2_message_id = 0

    message = await context.bot.send_message(event.chat_id, text, **send_args)
    return message.message_id


@log.log
async def cs2_sweep_callback(context: CallbackContext) -> None:
    """Keep one CS2 results message up to date through an event's evening.

    Posts as soon as the first match shows up on Leetify and edits that same message as each
    later match lands. Removes itself once the match list has been quiet for CS2_SWEEP_SETTLE,
    or once the deadline passes.
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

    now = datetime.datetime.now()
    expired = now >= data["deadline"]
    session = await event_session(get_client(), chat, event, context.application.user_data)

    if session is None:
        # Leetify unreachable - retry on the next pass rather than claim nobody played.
        if expired:
            logger.warning(
                "Giving up on CS2 results for chat_id=%s on %s: Leetify unreachable", job.chat_id, event_date
            )
            job.schedule_removal()
        return

    match_ids = {match.id for match in session.matches}
    changed = match_ids != data["seen"]
    if changed:
        data["seen"] = match_ids
        data["quiet_since"] = now

    if not match_ids:
        # Nothing to show yet. Early in the evening this is the normal case.
        if expired:
            logger.info("No CS2 matches found for chat_id=%s on %s; giving up", job.chat_id, event_date)
            job.schedule_removal()
        return

    # The night is over once no new match has appeared for a while, or once time runs out.
    final = expired or (now - data["quiet_since"]) >= CS2_SWEEP_SETTLE
    if not changed and not final:
        logger.debug("CS2 sweep for %s unchanged: %d match(es) so far", event_date, len(match_ids))
        return

    try:
        message_id = await _publish_cs2_results(context, event, render_results(session, live=not final))
    except TelegramError as e:
        # Leave the event unreported and the job alive, so the next pass can try again.
        logger.warning("Failed to write CS2 results for chat_id=%s on %s: %s", job.chat_id, event_date, e)
        return

    # Remember the message either way, so a restart edits it instead of posting a second one.
    event.update_cs2_progress(message_id, session.played_user_ids)

    if final:
        event.record_cs2_session(session.played_user_ids)
        job.schedule_removal()
        logger.info(
            "Finalised CS2 results for chat_id=%s on %s: %d match(es)",
            job.chat_id,
            event_date,
            len(session.matches),
        )
    else:
        logger.info(
            "Updated live CS2 results for chat_id=%s on %s: %d match(es) so far",
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
                    # Safety net for an event whose sweep never ran - the bot was down all
                    # evening, say. Normally the sweep started at the event's start time and
                    # is either still running or already done, and this is a no-op.
                    schedule_cs2_sweep(context.job_queue, chat.chat_id, event.event_date, event.start_time)
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
    # An upgrade spanning several releases outgrows Telegram's message limit; send the
    # announcement as consecutive messages rather than dropping the tail of it.
    chunks = split_for_telegram(text)
    for chat_id in bot_data.authorized_chats:
        try:
            for chunk in chunks:
                await bot.send_message(chat_id=chat_id, text=chunk)
            logger.info("Sent version announcement to chat_id=%s (%d message(s))", chat_id, len(chunks))
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

    # Start the CS2 sweep for any event happening today. Hourly rather than daily so it also
    # catches an event created on the day it happens, and starts right after boot because
    # jobs live only in memory - a restart would otherwise lose a sweep already in progress.
    application.job_queue.run_repeating(
        schedule_todays_cs2_sweeps_callback,
        interval=datetime.timedelta(hours=1),
        first=10,
        name="cs2_sweeps",
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
