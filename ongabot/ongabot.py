#!/usr/bin/env python3
"""An application that runs a telegram bot called ONGAbot"""

import datetime
import html
import logging
import os
import random
from typing import Any, Dict, List, Tuple, cast

from telegram import Bot, BotCommand, LinkPreviewOptions, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackContext, ContextTypes, JobQueue, PicklePersistence
from telegram.error import BadRequest, TelegramError

import eventcreator
from _version import __version__ as CURRENT_VERSION
from botdata import BotData
from chat import Chat
from cs2.leetify import get_client
from cs2.patchnotesformat import render_patch_notes_html
from cs2.report import event_session, render_results
from cs2.steamnews import SteamNewsItem
from cs2.steamnews import get_client as get_steam_news_client
from event import Event
from handler import AuthorizationHandler
from handler import AuthorizeCommandHandler
from handler import CancelEventCommandHandler
from handler import ChangelogCommandHandler
from handler import Cs2CommandHandler
from handler import Cs2PatchesCommandHandler
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
from handler import ShortsReactionHandler
from handler import StartCommandHandler
from handler import StatisticsCommandHandler
from handler import StatisticsSortCallbackHandler
from handler import TopicsCommandHandler
from handler import UnLinkSteamCommandHandler
from handler import UpdateEventCommandHandler
from jokes import get_client as get_joke_client
from quips import refresh_quip_pool
from userdata import UserData
from utils import log
from utils.changelog import get_changelog_delta, is_dev_version
from utils.changelogformat import render_changelog_html
from utils.commands import ALL_COMMANDS, BOT_DESCRIPTION, BOT_SHORT_DESCRIPTION
from utils.helper import parse_time
from utils.htmlblocks import send_html_with_fallback
from utils.points import render_event_recap_message
from youtube import client as youtube_client
from youtube.selection import pick_short
from youtube.topics import choose_topic, decay_topic_scores, register_topics

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


# The daytime window a chat's daily YouTube Short is randomly posted within, so it doesn't
# land at the same clock time (or at 3am) every day.
DEFAULT_SHORTS_WINDOW_START = datetime.time(10, 0)
DEFAULT_SHORTS_WINDOW_END = datetime.time(20, 0)


def _parse_window_time(env_var: str, default: datetime.time) -> datetime.time:
    raw = os.getenv(env_var)
    if not raw:
        return default
    try:
        return parse_time(raw)
    except ValueError:
        logger.warning("Ignoring malformed %s=%r; using %s", env_var, raw, default)
        return default


def shorts_window() -> Tuple[datetime.time, datetime.time]:
    """The daytime window (start, end) a chat's daily Short is randomly posted within.

    YOUTUBE_SHORTS_WINDOW_START/_END override the defaults, each as "HH:MM". Read on every
    call, like cs2.session.min_members, so a change takes effect on the next scheduling pass
    without a restart. Falls back to the defaults, with a warning, when the configured window
    is inverted or empty - an overnight window isn't supported, and a silently empty window
    would otherwise never post anything.
    """
    start = _parse_window_time("YOUTUBE_SHORTS_WINDOW_START", DEFAULT_SHORTS_WINDOW_START)
    end = _parse_window_time("YOUTUBE_SHORTS_WINDOW_END", DEFAULT_SHORTS_WINDOW_END)
    if start >= end:
        logger.warning(
            "YOUTUBE_SHORTS_WINDOW_START=%s is not before YOUTUBE_SHORTS_WINDOW_END=%s; using the defaults",
            start,
            end,
        )
        return DEFAULT_SHORTS_WINDOW_START, DEFAULT_SHORTS_WINDOW_END
    return start, end


def shorts_job_name(chat_id: int, post_date: datetime.date) -> str:
    """Name of today's Short-posting job for one chat. Also the guard against double-scheduling."""
    return f"youtube_short_{chat_id}_{post_date}"


def schedule_todays_short(job_queue: JobQueue, chat: Chat, today: datetime.date, now: datetime.datetime) -> None:
    """Pick a random time left in today's window and schedule this chat's post.

    A no-op when the chat already posted today, a job for today is already scheduled, or the
    window has already closed for today - the last case means a chat with no window left
    simply waits for tomorrow's pass rather than posting outside its configured hours.
    """
    if chat.last_shorts_posted_date == today:
        return

    name = shorts_job_name(chat.chat_id, today)
    if job_queue.get_jobs_by_name(name):
        logger.debug("Shorts post %s is already scheduled", name)
        return

    window_start, window_end = shorts_window()
    window_end_dt = datetime.datetime.combine(today, window_end)
    if now >= window_end_dt:
        logger.debug("Shorts window for chat_id=%s closed for %s; nothing scheduled", chat.chat_id, today)
        return

    window_start_dt = max(now, datetime.datetime.combine(today, window_start))
    span = max((window_end_dt - window_start_dt).total_seconds(), 0.0)
    post_at = window_start_dt + datetime.timedelta(seconds=random.uniform(0, span))
    job_queue.run_once(post_shorts_callback, when=post_at, chat_id=chat.chat_id, name=name)
    logger.info(
        "Scheduled YouTube Short for chat_id=%s at %s (window %s-%s)",
        chat.chat_id,
        post_at,
        window_start,
        window_end,
    )


@log.log
async def schedule_todays_shorts_callback(context: CallbackContext) -> None:
    """Re-derive and (re-)schedule today's Short for every authorized chat, hourly.

    Jobs aren't persisted - PicklePersistence stores bot_data, not the JobQueue - so this is
    also what resumes a lost post-time choice after a restart: a restart before the chosen
    time re-rolls a fresh random time rather than resuming the exact original pick, the same
    trade-off schedule_todays_cs2_sweeps_callback accepts.
    """
    bot_data: BotData = context.bot_data
    now = datetime.datetime.now()
    for chat_id in bot_data.authorized_chats:
        schedule_todays_short(context.job_queue, bot_data.get_chat(chat_id), now.date(), now)


@log.log
async def post_shorts_callback(context: CallbackContext) -> None:
    """Post one YouTube Short to a chat, topic chosen from its learned per-chat preferences.

    Tries a second topic if the first yields nothing (an empty search or an all-duplicate
    result is not unusual for a niche topic). If still nothing, the chat is left unposted for
    today so the next hourly re-derivation pass retries later in the window, rather than
    losing the day's post to one bad search.
    """
    job = context.job
    bot_data: BotData = context.bot_data
    chat = bot_data.get_chat(job.chat_id)
    if chat.last_shorts_posted_date == datetime.date.today():
        return

    client = youtube_client.get_client()
    topic = choose_topic(chat.topic_scores)
    used_topic = topic
    video = await pick_short(client, chat, topic)
    if video is None:
        # Exclude the topic already tried, so a coin-flip re-draw can't waste the retry on
        # the same topic - and skip the retry entirely when it's the only one tracked.
        remaining_scores = {t: s for t, s in chat.topic_scores.items() if t != topic}
        if remaining_scores:
            used_topic = choose_topic(remaining_scores)
            video = await pick_short(client, chat, used_topic)
    if video is None:
        logger.warning("No eligible Short found for chat_id=%s (topic=%s); skipping today", job.chat_id, used_topic)
        return

    try:
        message = await context.bot.send_message(chat.chat_id, video.url)
    except TelegramError as e:
        logger.error("Failed to post YouTube Short to chat_id=%s: %s", job.chat_id, e)
        return

    chat.record_shorts_post(message.message_id, video, datetime.datetime.now())
    register_topics(chat.topic_scores, video.topics)
    logger.info(
        "Posted YouTube Short to chat_id=%s: video_id=%s chosen_topic=%s extracted_topics=%s",
        job.chat_id,
        video.video_id,
        used_topic,
        video.topics,
    )


@log.log
async def decay_shorts_topic_scores_callback(context: CallbackContext) -> None:
    """Nightly pull every chat's topic scores a little toward neutral."""
    bot_data: BotData = context.bot_data
    for chat in bot_data.chats.values():
        decay_topic_scores(chat.topic_scores)


@log.log
async def refresh_quip_pool_callback(context: CallbackContext) -> None:  # pylint: disable=unused-argument
    """Periodically refresh the dynamic No-op/Maybe-Baby quip pool from JokeAPI.

    Takes no per-chat state, but job_queue always passes a CallbackContext.
    """
    await refresh_quip_pool(get_joke_client())


DEFAULT_CS2_PATCHNOTES_POLL_MINUTES = 20


def cs2_patchnotes_poll_interval() -> datetime.timedelta:
    """How often to poll Steam for new CS2 patch notes.

    CS2_PATCHNOTES_POLL_MINUTES overrides the default. Read once, when the job is registered
    at startup, so a change needs a restart - unlike shorts_window, the interval of a running
    repeating job cannot change under it.
    """
    default = datetime.timedelta(minutes=DEFAULT_CS2_PATCHNOTES_POLL_MINUTES)
    raw = os.getenv("CS2_PATCHNOTES_POLL_MINUTES")
    if not raw:
        return default
    try:
        minutes = int(raw)
    except ValueError:
        minutes = 0
    if minutes <= 0:
        logger.warning("Ignoring malformed CS2_PATCHNOTES_POLL_MINUTES=%r; using %s", raw, default)
        return default
    return datetime.timedelta(minutes=minutes)


async def _announce_cs2_patch_notes(bot: Bot, bot_data: BotData, items: List[SteamNewsItem]) -> None:
    """Send new CS2 patch notes to every subscribed chat, in the order given."""
    messages = render_patch_notes_html(items)
    # A snapshot: /cs2patches can change the set while this awaits a send.
    for chat_id in list(bot_data.cs2_patchnotes_subscribers):
        try:
            for message in messages:
                await send_html_with_fallback(bot, chat_id, message)
            logger.info("Sent %d CS2 patch note(s) to chat_id=%s (%d message(s))", len(items), chat_id, len(messages))
        except TelegramError as e:
            logger.error("Failed to send CS2 patch notes to chat_id=%s: %s", chat_id, e)


@log.log
async def cs2_patchnotes_sweep_callback(context: CallbackContext) -> None:
    """Poll Steam for CS2 patch notes and announce any not seen before to subscribed chats.

    The first successful poll only records what Steam lists, so neither a fresh deployment
    nor an upgrade floods the chats with weeks of old patches. After that, patches that
    appeared since the last poll are announced oldest first. An unreachable feed changes
    nothing and is retried on the next poll.
    """
    bot_data: BotData = context.bot_data
    items = await get_steam_news_client().get_cs2_patch_notes()
    if items is None:
        return

    seen = bot_data.cs2_patchnotes_seen_gids
    if seen is None:
        # An empty feed is left unprimed: priming on it would make the next real fetch
        # announce everything.
        if items:
            bot_data.cs2_patchnotes_seen_gids = {item.gid for item in items}
            logger.info("Started tracking CS2 patch notes: %d already published, none announced", len(items))
        return

    # gid is only an identity; Steam's publish date is what orders patches.
    new_items = sorted((item for item in items if item.gid not in seen), key=lambda item: item.date)
    if not new_items:
        logger.debug("No new CS2 patch notes among %d listed", len(items))
        return

    logger.info("Found %d new CS2 patch note(s): %s", len(new_items), [item.gid for item in new_items])
    if bot_data.cs2_patchnotes_subscribers:
        await _announce_cs2_patch_notes(context.bot, bot_data, new_items)
    seen.update(item.gid for item in new_items)


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
    session = await event_session(get_client(), chat, event_date, context.application.user_data)

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
    """Send a version-change announcement to all authorized chats.

    Each release in the delta renders as a visible header line with its body collapsed, so
    an upgrade spanning several releases stays a few lines in the chat until someone opens
    it. An upgrade long enough to outgrow Telegram's message limit is still split across
    consecutive messages rather than having its tail dropped.
    """
    delta = get_changelog_delta(old_version, new_version)
    headline = f"ONGAbot updated to <b>v{html.escape(new_version, quote=False)}</b>!"
    messages = render_changelog_html(delta, headline=headline)

    for chat_id in bot_data.authorized_chats:
        try:
            for message in messages:
                await send_html_with_fallback(bot, chat_id, message)
            logger.info("Sent version announcement to chat_id=%s (%d message(s))", chat_id, len(messages))
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

    # Same reasoning as the CS2 sweep above: hourly re-derivation both catches a chat
    # authorized partway through the day and resumes a lost post-time choice after a restart.
    application.job_queue.run_repeating(
        schedule_todays_shorts_callback,
        interval=datetime.timedelta(hours=1),
        first=15,
        name="youtube_shorts_schedule",
    )
    application.job_queue.run_daily(
        decay_shorts_topic_scores_callback, time=datetime.time(0, 10, 0), name="decay_shorts_topic_scores"
    )

    # Keeps the No-op/Maybe-Baby quip pool dynamic rather than a fixed list. Every 6 hours is
    # plenty for a joke pool; starts right after boot so a restart doesn't leave the fallback
    # list in place for hours.
    application.job_queue.run_repeating(
        refresh_quip_pool_callback,
        interval=datetime.timedelta(hours=6),
        first=20,
        name="quip_pool_refresh",
    )

    # Valve ships patches at any hour, so this polls around the clock. Starts right after boot
    # so a restart does not hold back a patch note by a whole interval.
    application.job_queue.run_repeating(
        cs2_patchnotes_sweep_callback,
        interval=cs2_patchnotes_poll_interval(),
        first=25,
        name="cs2_patchnotes_sweep",
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
    application.add_handler(Cs2PatchesCommandHandler())
    application.add_handler(LinkSteamCommandHandler())
    application.add_handler(UnLinkSteamCommandHandler())
    application.add_handler(TopicsCommandHandler())
    application.add_handler(ShortsReactionHandler())
    application.add_error_handler(error)

    # Start the bot. message_reaction is opt-in and not delivered by default - without
    # allowed_updates, ShortsReactionHandler would silently never fire.
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
