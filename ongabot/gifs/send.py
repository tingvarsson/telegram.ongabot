"""The one way a moment goes out: as a GIF with its text as the caption, or as the plain text.

A GIF never stands between the group and the message itself. GIFs switched off with /gifs, a
missing API key, a failed search, nothing left to pick and Telegram refusing the animation all
end the same way: the plain text goes out exactly as it did before GIFs existed.
"""

import logging
from typing import Any, Optional

from telegram import Bot, Message
from telegram.error import TelegramError, TimedOut

from chat import Chat
from gifs.moods import Mood
from gifs.picker import pick_gif

_logger = logging.getLogger(__name__)

# Seconds to wait for Telegram to answer a send_animation. Telegram fetches the mp4 from Giphy
# before it answers, which can outlast python-telegram-bot's 5 s default; a timeout is costly
# here, since the text is then not sent (see send_with_gif).
ANIMATION_READ_TIMEOUT = 15.0


async def _send_animation(bot: Bot, chat_id: int, mood: Mood, text: str, send_kwargs: Any) -> Optional[Message]:
    """Pick and send a GIF for mood with text as its caption, or None (logged) when that fails.

    Raises TimedOut, since the animation may still arrive.
    """
    picked = await pick_gif(chat_id, mood)
    if picked is None:
        _logger.info("No GIF for mood=%s in chat_id=%s: no GIF found", mood.name, chat_id)
        return None
    try:
        message = await bot.send_animation(
            chat_id, picked.gif.mp4_url, caption=text, read_timeout=ANIMATION_READ_TIMEOUT, **send_kwargs
        )
    except TimedOut:
        raise
    except TelegramError as e:
        # A caption over Telegram's 1024-character limit lands here too.
        _logger.warning("Failed to send GIF gif_id=%s to chat_id=%s: %s", picked.gif.gif_id, chat_id, e)
        return None
    _logger.info(
        "Sent GIF gif_id=%s to chat_id=%s (mood=%s, phrase=%r)", picked.gif.gif_id, chat_id, mood.name, picked.phrase
    )
    return message


async def send_with_gif(
    bot: Bot, chat: Chat, text: str, mood: Optional[Mood], *, text_fallback: bool = True, **send_kwargs: Any
) -> Optional[Message]:
    """Send text to chat with a GIF for mood, falling back to the plain text.

    send_kwargs (parse_mode, reply_parameters, disable_notification...) go to whichever of
    send_animation and send_message ends up sending. A mood of None sends the plain text, for a
    moment that gets no GIF this time. With text_fallback False the GIF is all there is: nothing
    is sent without one. Otherwise only a failure of the plain text raises, so a caller keeps
    the error handling it had for send_message.

    A GIF that timed out sends nothing more and returns None: Telegram may still deliver it, and
    the text on top would post the moment twice.
    """
    chat_id = chat.chat_id
    if mood is not None:
        if not chat.gifs_enabled:
            _logger.info("No GIF for mood=%s in chat_id=%s: GIFs are off", mood.name, chat_id)
        else:
            try:
                message = await _send_animation(bot, chat_id, mood, text, send_kwargs)
            except TimedOut as e:
                _logger.warning(
                    "Sending a %s GIF to chat_id=%s timed out; it may still arrive, so the text is not sent: %s",
                    mood.name,
                    chat_id,
                    e,
                )
                return None
            if message is not None:
                return message

    if not text_fallback:
        return None
    return await bot.send_message(chat_id, text, **send_kwargs)
