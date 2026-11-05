"""One-line summaries of incoming updates, for the INFO log."""

import logging
import re

from telegram import Chat, Update

# Telegram's shape for a command: "/" plus up to 32 letters, digits or underscores, then an
# optional @botname. Anything else starting with "/" (a pasted path, say) is not a command.
_COMMAND = re.compile(r"/[A-Za-z0-9_]{1,32}(@\w+)?")


def command_of(update: Update) -> str | None:
    """The command an update's message starts with, lowercased and without @botname."""
    msg = update.effective_message
    if msg and msg.text and msg.text.startswith("/"):
        first = msg.text.split()[0]
        if _COMMAND.fullmatch(first):
            return first.split("@")[0].lower()
    return None


def update_kind(update: Update) -> str:
    """The name of the update's payload field, e.g. "message", "poll" or "edited_message"."""
    return next((str(kind) for kind in Update.ALL_TYPES if getattr(update, kind, None) is not None), "unknown")


def _origin(update: Update) -> str:
    """Who sent an update and where, e.g. "from user_id=7 in chat_id=-100123 (supergroup)"."""
    parts = []
    sender = update.effective_sender
    if isinstance(sender, Chat):
        # An anonymous admin or a channel speaking as a chat rather than as a user.
        parts.append(f"from sender_chat_id={sender.id}")
    elif sender is not None:
        parts.append(f"from user_id={sender.id}")
    if update.effective_chat:
        parts.append(f"in chat_id={update.effective_chat.id} ({update.effective_chat.type})")
    return " ".join(parts)


def _summary(update: Update) -> tuple[int, str]:
    """What the update is, with the level to log it at; see describe_update()."""
    command = command_of(update)
    if update.message and command:
        return logging.INFO, command
    if update.edited_message and command:
        # Command handlers also answer edited messages, so an edited command is acted on too.
        return logging.INFO, f"{command} (edited)"

    if update.callback_query:
        return logging.INFO, f"button {update.callback_query.data!r}"

    if update.poll_answer:
        answer = update.poll_answer
        vote = f"options {list(answer.option_ids)}" if answer.option_ids else "retracted vote"
        return logging.INFO, f"poll answer ({vote}) on poll_id={answer.poll_id}"

    if update.my_chat_member:
        return logging.INFO, f"bot membership is now {update.my_chat_member.new_chat_member.status}"

    return logging.DEBUG, update_kind(update)


def describe_update(update: Update) -> tuple[int, str]:
    """A short summary of what an update is and who sent it, with the level to log it at.

    Commands, button taps, poll votes and changes to the bot's own membership are user actions
    and summarized at INFO. Everything else (plain messages, poll state, service messages) is
    DEBUG, so a group with privacy mode off does not flood the log. Message text beyond the
    command itself is never included: it is chat content, and arguments can carry things like
    Steam profile links.
    """
    level, what = _summary(update)
    return level, f"{what} {_origin(update)}".rstrip()
