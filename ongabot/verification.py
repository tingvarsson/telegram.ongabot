"""Joke age verification: the group votes a member unverified (🔞), or verified again.

/unverify and /verify post a Yes/No poll about one member. After VOTE_DURATION the poll is
stopped and tallied: it passes with more yes than no and at least MIN_YES_VOTES yes. An
unverified member gets BADGE next to their name and has their event votes roasted (see
quips.Banter.UNVERIFIED). It is banter only - votes, points and statistics are unaffected.

Open votes are persisted on the Chat, but their close jobs live only in the job queue, so
reschedule_open_votes re-creates them on startup.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Iterable, Optional

from telegram import Bot, ReplyParameters
from telegram.error import TelegramError
from telegram.ext import CallbackContext, JobQueue
from telegram.helpers import escape_markdown

from utils.log import log

if TYPE_CHECKING:
    from chat import Chat

_logger = logging.getLogger(__name__)

VOTE_DURATION = timedelta(hours=1)
MIN_YES_VOTES = 3
BADGE = "🔞"
# Poll options, in this order: the tally reads option 0 as yes and option 1 as no.
VOTE_OPTIONS = ["Yes", "No"]


@dataclass
class VerificationVote:
    """An open /unverify or /verify vote, persisted on its Chat until it closes.

    Attributes:
        poll_id: id of the Yes/No poll
        chat_id: chat the poll was posted in
        message_id: message holding the poll, needed to stop it
        target_id: user id of the member being voted on
        target_name: the member's first name, for the poll question and the verdict
        unverify: True for /unverify, False for /verify
        closes_at: when the poll is stopped and tallied (UTC)
    """

    poll_id: str
    chat_id: int
    message_id: int
    target_id: int
    target_name: str
    unverify: bool
    closes_at: datetime


def vote_passes(yes: int, no: int) -> bool:
    """A vote passes with a majority of yes, and at least MIN_YES_VOTES of them."""
    return yes >= MIN_YES_VOTES and yes > no


def badged(name: str, unverified: bool) -> str:
    """Prefix name with the unverified badge when unverified."""
    return f"{BADGE} {name}" if unverified else name


def poll_question(target_name: str, unverify: bool) -> str:
    """The question of the Yes/No poll."""
    if unverify:
        return f"Unverify {target_name}? {BADGE}"
    return f"Verify {target_name} again? ✅"


def verdict_text(vote: VerificationVote, yes: int, no: int) -> str:
    """The message posted when a vote closes."""
    name = vote.target_name
    score = f"{yes}–{no}"
    if vote_passes(yes, no):
        if vote.unverify:
            return f"{BADGE} The council has spoken ({score}): {name} is officially unverified. Ask a grown-up."
        return f"✅ The council has spoken ({score}): {name} is verified again. Welcome back to adulthood."
    needed = f"{MIN_YES_VOTES} yes and a majority needed"
    if vote.unverify:
        return f"Not enough evidence ({score}, {needed}). {name} keeps their ID, for now."
    return f"Verification denied ({score}, {needed}). {name} stays {BADGE}."


def unverified_footer(names: Iterable[str]) -> Optional[str]:
    """A MarkdownV2 line listing the unverified members, or None when there are none.

    Used below the /leaderboard and /statistics tables, whose fixed-width name cells strip
    emoji, so the badge cannot sit next to the name there.
    """
    names = sorted(names, key=str.casefold)
    if not names:
        return None
    return escape_markdown(f"{BADGE} Unverified: {', '.join(names)}", version=2)


def _close_job_name(poll_id: str) -> str:
    """Name of the job that closes one vote."""
    return f"verification_vote:{poll_id}"


def schedule_close(job_queue: JobQueue, vote: VerificationVote, now: Optional[datetime] = None) -> None:
    """Schedule the close of vote at vote.closes_at, or right away if that has passed."""
    now = now or datetime.now(timezone.utc)
    # A relative delay rather than the datetime itself: a close time that passed while the bot
    # was down must still fire, not be dropped as a misfire.
    delay = max(vote.closes_at - now, timedelta(0))
    job_queue.run_once(
        close_vote_callback,
        when=delay,
        chat_id=vote.chat_id,
        name=_close_job_name(vote.poll_id),
        data=vote.poll_id,
    )
    _logger.info(
        "Scheduled close of verification vote poll_id=%s in chat_id=%s in %s",
        vote.poll_id,
        vote.chat_id,
        delay,
    )


async def start_vote(
    bot: Bot, job_queue: JobQueue, chat: "Chat", target_id: int, target_name: str, unverify: bool
) -> VerificationVote:
    """Post the Yes/No poll about target, store it on chat and schedule its close."""
    message = await bot.send_poll(
        chat.chat_id,
        poll_question(target_name, unverify),
        VOTE_OPTIONS,
        is_anonymous=False,
    )
    vote = VerificationVote(
        poll_id=message.poll.id,
        chat_id=chat.chat_id,
        message_id=message.message_id,
        target_id=target_id,
        target_name=target_name,
        unverify=unverify,
        closes_at=datetime.now(timezone.utc) + VOTE_DURATION,
    )
    chat.add_verification_vote(vote)
    schedule_close(job_queue, vote)
    _logger.info(
        "Started %s vote poll_id=%s on user_id=%s in chat_id=%s",
        "unverify" if unverify else "verify",
        vote.poll_id,
        target_id,
        chat.chat_id,
    )
    return vote


async def _redraw_status_messages(bot: Bot, chat: "Chat", user_id: int) -> None:
    """Redraw the status message of every open event user_id has voted on, so the badge
    appears (or goes) right away rather than on that event's next vote."""
    for event in chat.active_events:
        # Only events that list the member: redrawing any other would be an unchanged edit,
        # which Telegram rejects.
        if not any(user.id == user_id for user in event.poll_answers):
            continue
        try:
            await event.update_status_message(bot, unverified=chat.unverified)
        except TelegramError as e:
            _logger.warning("Could not redraw status message of poll_id=%s: %s", event.poll_id, e)


@log
async def close_vote_callback(context: CallbackContext) -> None:
    """Stop a vote's poll, tally it, apply the result and post the verdict."""
    if context.job is None or context.job.chat_id is None:
        _logger.error("Verification vote close ran without a job or chat")
        return
    # Job.data is typed as object by python-telegram-bot; this job always sets the poll id.
    poll_id = str(context.job.data)
    chat = context.bot_data.get_chat(context.job.chat_id)
    vote = chat.pop_verification_vote(poll_id)
    if vote is None:
        _logger.warning("No open verification vote for poll_id=%s in chat_id=%s", poll_id, chat.chat_id)
        return

    try:
        poll = await context.bot.stop_poll(vote.chat_id, vote.message_id)
    except TelegramError as e:
        # Most likely the poll message was deleted. The vote cannot be tallied, so it is dropped.
        _logger.warning("Could not stop verification poll_id=%s, dropping the vote: %s", poll_id, e)
        return

    yes, no = poll.options[0].voter_count, poll.options[1].voter_count
    passed = vote_passes(yes, no)
    _logger.info(
        "Closed %s vote poll_id=%s on user_id=%s: yes=%d no=%d passed=%s",
        "unverify" if vote.unverify else "verify",
        poll_id,
        vote.target_id,
        yes,
        no,
        passed,
    )
    if passed:
        chat.set_unverified(vote.target_id, vote.target_name, vote.unverify)
        await _redraw_status_messages(context.bot, chat, vote.target_id)

    await context.bot.send_message(
        vote.chat_id,
        verdict_text(vote, yes, no),
        reply_parameters=ReplyParameters(vote.message_id, allow_sending_without_reply=True),
    )


def reschedule_open_votes(chats: Iterable["Chat"], job_queue: JobQueue) -> None:
    """Re-create the close jobs of every open vote, since jobs are not persisted."""
    now = datetime.now(timezone.utc)
    for chat in chats:
        for vote in list(chat.verification_votes.values()):
            schedule_close(job_queue, vote, now)
