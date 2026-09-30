"""Poke the regulars who have not voted yet, on the morning of an event that is short a stack.

POKE_LEAD_HOURS before an event starts, if no time slot has a full five-stack yet, the bot
posts one message that @-mentions everyone who voted in one of the chat's recent polls but not
in this one. The Bot API cannot list a group's members, so "recent voters" is the closest thing
to the group's roster the bot has.

Like the CS2 sweep, the job lives in memory only: an hourly pass re-derives it for today's
events, which is also what resumes a poke a restart dropped. Event.poked is persisted, so a
restart never pokes twice.
"""

import datetime
import html
import logging
import math
import os
from typing import Collection, Dict, List

from telegram import Bot, ReplyParameters, User
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.error import TelegramError
from telegram.ext import CallbackContext, JobQueue

from botdata import BotData
from chat import Chat
from event import Event
from quips import Banter, next_banter
from utils import log
from verification import badged

_logger = logging.getLogger(__name__)

# How long before the start the poke goes out: early on the event day for the default 18:30.
DEFAULT_POKE_LEAD_HOURS = 10.0
# Votes one slot needs before the event counts as a full stack, and nobody is poked.
FULL_STACK = 5
# How many of the chat's latest events count towards its regulars. About two months of weekly
# polls: long enough to include someone who skipped a few, short enough to drop the departed.
POKE_RECENT_EVENTS = 8

# Statuses of someone who is no longer in the group, and must not be pinged.
_GONE_STATUSES = {ChatMemberStatus.LEFT, ChatMemberStatus.BANNED}


def poke_lead_time() -> datetime.timedelta:
    """How long before an event's start time the poke goes out.

    POKE_LEAD_HOURS overrides the default, fractions allowed (0.1 is six minutes, handy on a dev
    bot). A bad value logs a warning and falls back to the default.
    """
    raw = os.getenv("POKE_LEAD_HOURS")
    if not raw:
        return datetime.timedelta(hours=DEFAULT_POKE_LEAD_HOURS)
    try:
        hours = float(raw)
    except ValueError:
        _logger.warning("Ignoring non-numeric POKE_LEAD_HOURS=%r; using %s", raw, DEFAULT_POKE_LEAD_HOURS)
        return datetime.timedelta(hours=DEFAULT_POKE_LEAD_HOURS)
    if not math.isfinite(hours) or hours < 0:
        _logger.warning("Ignoring POKE_LEAD_HOURS=%r; using %s", raw, DEFAULT_POKE_LEAD_HOURS)
        return datetime.timedelta(hours=DEFAULT_POKE_LEAD_HOURS)
    return datetime.timedelta(hours=hours)


def _starts_at(event: Event, tz: datetime.tzinfo) -> datetime.datetime:
    """When event starts, as an aware datetime in the chat's zone tz."""
    return datetime.datetime.combine(event.event_date, event.start_time, tzinfo=tz)


def poke_time(event: Event, tz: datetime.tzinfo) -> datetime.datetime:
    """When the poke for event is due, in the chat's zone tz: the lead time before its start,
    but never before its day.

    The clamp keeps an early start, or a long lead time, from poking the evening before.
    """
    day_start = datetime.datetime.combine(event.event_date, datetime.time.min, tzinfo=tz)
    return max(_starts_at(event, tz) - poke_lead_time(), day_start)


def poke_job_name(chat_id: int, event_date: datetime.date) -> str:
    """Name of the poke job for one chat's event. Also the guard against scheduling twice."""
    return f"poke_{chat_id}_{event_date}"


def schedule_poke(job_queue: JobQueue, chat_id: int, event: Event, now: datetime.datetime) -> None:
    """Schedule the poke for event, or run it right away if it is already due.

    now is aware, in the chat's zone, which the event's wall-clock times are read in. A no-op
    for an event that is already poked, cancelled, completed or under way, and when the job is
    already scheduled.
    """
    if event.poked or event.cancelled or event.completed:
        return
    tz = now.tzinfo
    if now >= _starts_at(event, tz):
        _logger.debug("Event on %s in chat_id=%s has started; no poke scheduled", event.event_date, chat_id)
        return

    name = poke_job_name(chat_id, event.event_date)
    if job_queue.get_jobs_by_name(name):
        _logger.debug("Poke %s is already scheduled", name)
        return

    # Aware in the chat's zone: the JobQueue would read a naive datetime as UTC.
    when = max(now, poke_time(event, tz))
    job_queue.run_once(poke_callback, when=when, chat_id=chat_id, name=name, data=event.event_date)
    _logger.info("Scheduled poke for chat_id=%s event_date=%s at %s", chat_id, event.event_date, when)


@log.log
async def schedule_todays_pokes_callback(context: CallbackContext) -> None:
    """Schedule the poke for every chat with an event today.

    Runs hourly, and scheduling is idempotent, so this covers an event created on its own day as
    well as the daily rollover, and resumes a poke a restart dropped.
    """
    bot_data: BotData = context.bot_data

    for chat in bot_data.chats.values():
        now = chat.now()
        event = chat.get_event_by_date(now.date())
        if event is None:
            continue
        schedule_poke(context.job_queue, chat.chat_id, event, now)


def recent_voters(chat: Chat, limit: int) -> List[User]:
    """Everyone who voted on one of chat's latest limit events, newest voters first.

    The Bot API cannot list a group's members, so this is the closest thing to a roster.
    Cancelled events are skipped, like everywhere else they would skew who counts. A user is
    listed once, under the User object of their newest vote.
    """
    events = sorted((e for e in chat.events.values() if not e.cancelled), key=lambda e: e.event_date, reverse=True)
    voters: Dict[int, User] = {}
    for event in events[:limit]:
        for user in event.poll_answers:
            voters.setdefault(user.id, user)
    return list(voters.values())


async def _still_in_group(bot: Bot, chat_id: int, user: User) -> bool:
    """False only when Telegram says user has left or was removed from chat_id.

    Unlike utils.dm.is_group_member, a failed lookup keeps the user: better one stray ping
    than no poke at all when the check itself is broken.
    """
    try:
        member = await bot.get_chat_member(chat_id, user.id)
    except TelegramError as e:
        _logger.warning("Could not check user_id=%s in chat_id=%s, poking anyway: %s", user.id, chat_id, e)
        return True
    if member.status == ChatMemberStatus.RESTRICTED:
        # A restricted user is still in the group, unless they left it while restricted.
        return bool(getattr(member, "is_member", True))
    return member.status not in _GONE_STATUSES


async def poke_candidates(bot: Bot, chat: Chat, event: Event) -> List[User]:
    """The chat's recent voters who have no vote on event and are still in the group."""
    voted = event.voted_user_ids()
    candidates = [user for user in recent_voters(chat, POKE_RECENT_EVENTS) if user.id not in voted]
    return [user for user in candidates if await _still_in_group(bot, chat.chat_id, user)]


def render_poke_message(event: Event, users: List[User], unverified: Collection[int] = ()) -> str:
    """The poke itself, as HTML: the state of the poll, then everyone it pings, then banter.

    unverified user ids get the 🔞 badge, as everywhere else a name is shown.
    """
    mentions = ", ".join(badged(user.mention_html(), user.id in unverified) for user in users)
    start = html.escape(event.start_time.strftime("%H.%M"))
    return f"Game night at {start} and no slot has five yet.\n{mentions} — {html.escape(next_banter(Banter.POKE))}"


@log.log
async def poke_callback(context: CallbackContext) -> None:
    """Send the poke for one event, if it is still short a stack and anyone has not voted."""
    job = context.job
    if job is None or job.chat_id is None:
        _logger.error("Poke ran without a job")
        return
    # Job.data is typed as object by python-telegram-bot; this job always sets the event date.
    event_date = job.data
    chat: Chat = context.bot_data.get_chat(job.chat_id)
    event = chat.get_event_by_date(event_date)  # type: ignore[arg-type]

    # Re-checked here, since the event may have changed after the job was scheduled - an
    # /updateevent to an earlier start, say, leaves this job at the old time.
    if event is None or event.poked or event.cancelled or event.completed:
        _logger.info("Skipping poke for chat_id=%s on %s: event gone, poked or closed", job.chat_id, event_date)
        return
    if chat.now() >= _starts_at(event, chat.tz):
        _logger.info("Skipping poke for chat_id=%s on %s: the event has started", job.chat_id, event_date)
        return

    # Claimed before the first await: the JobQueue forgets a one-off job as soon as it starts,
    # so an hourly pass landing while the membership lookups run would otherwise schedule a
    # second poke. Released again below if the send fails, so the next pass retries.
    event.poked = True
    if event.has_full_stack(FULL_STACK):
        _logger.info("Skipping poke for chat_id=%s on %s: a slot has a full stack", job.chat_id, event_date)
        return

    users = await poke_candidates(context.bot, chat, event)
    if not users:
        _logger.info("Skipping poke for chat_id=%s on %s: every regular has voted", job.chat_id, event_date)
        return

    # Replies to the poll so the ping lands next to it, as long as it is still pinned. A poll
    # deleted since then must not stop the poke, hence allow_sending_without_reply.
    poll_message = chat.pinned_polls.get(event.poll_id)
    reply = ReplyParameters(poll_message.message_id, allow_sending_without_reply=True) if poll_message else None
    try:
        await context.bot.send_message(
            job.chat_id,
            render_poke_message(event, users, chat.unverified),
            parse_mode=ParseMode.HTML,
            reply_parameters=reply,
        )
    except TelegramError as e:
        # Released, so the next hourly pass retries until the event starts.
        event.poked = False
        _logger.warning("Failed to send poke for chat_id=%s on %s: %s", job.chat_id, event_date, e)
        return
    _logger.info("Poked %d member(s) for chat_id=%s on %s", len(users), job.chat_id, event_date)
