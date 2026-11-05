"""One-line summaries of incoming updates, for the INFO log."""

import logging

from telegram import Update


def command_of(update: Update) -> str | None:
    """The command an update's message starts with, lowercased and without @botname."""
    msg = update.effective_message
    if msg and msg.text and msg.text.startswith("/"):
        return msg.text.split()[0].split("@")[0].lower()
    return None


def _origin(update: Update) -> str:
    """Who sent an update and where, e.g. "from user_id=7 in chat_id=-100123 (supergroup)"."""
    parts = []
    if update.effective_user:
        parts.append(f"from user_id={update.effective_user.id}")
    if update.effective_chat:
        parts.append(f"in chat_id={update.effective_chat.id} ({update.effective_chat.type})")
    return " ".join(parts)


def _kind(update: Update) -> str:
    """The name of the update's payload field, e.g. "message", "poll" or "edited_message"."""
    return next((str(kind) for kind in Update.ALL_TYPES if getattr(update, kind, None) is not None), "unknown")


def describe_update(update: Update) -> tuple[int, str]:
    """A short summary of what an update is and who sent it, with the level to log it at.

    Commands, button taps, poll votes and changes to the bot's own membership are user actions
    and summarized at INFO. Everything else (plain messages, poll state, edits) is DEBUG, so a
    group with privacy mode off does not flood the log. Message text beyond the command itself is
    never included: it is chat content, and arguments can carry things like Steam profile links.
    """
    origin = _origin(update)

    command = command_of(update)
    if update.message and command:
        return logging.INFO, f"{command} {origin}"

    if update.callback_query:
        return logging.INFO, f"button {update.callback_query.data!r} {origin}"

    if update.poll_answer:
        answer = update.poll_answer
        vote = f"options {list(answer.option_ids)}" if answer.option_ids else "retracted vote"
        return logging.INFO, f"poll answer ({vote}) on poll_id={answer.poll_id} {origin}"

    if update.my_chat_member:
        status = update.my_chat_member.new_chat_member.status
        return logging.INFO, f"bot membership is now {status} {origin}"

    return logging.DEBUG, f"{_kind(update)} {origin}".rstrip()
