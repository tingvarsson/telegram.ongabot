"""This module contains log decorator and the bot-token log redaction."""

import functools
import inspect
import logging
import re
import traceback
from typing import Any, Callable, TypeVar, cast

F = TypeVar("F", bound=Callable[..., Any])  # pylint: disable=invalid-name

# A Bot API token is "<bot id>:<secret>". It ends up in logs inside API URLs
# ("https://api.telegram.org/bot<token>/getMe"): python-telegram-bot logs them at DEBUG,
# httpx at INFO, and HTTP errors carry them in exception messages.
_BOT_TOKEN = re.compile(r"\d{5,}:[A-Za-z0-9_-]{30,}")
TOKEN_PLACEHOLDER = "<bot-token>"


class TokenRedactingFilter(logging.Filter):  # pylint: disable=too-few-public-methods  # filter() is the API
    """Mask Telegram bot tokens in a record's message and traceback before it is written."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = _BOT_TOKEN.sub(TOKEN_PLACEHOLDER, message)
        if redacted != message:
            record.msg = redacted
            record.args = None
        if record.exc_info and not record.exc_text:
            # Formatter reuses exc_text when set, so the traceback is only rendered (redacted) once.
            text = "".join(traceback.format_exception(*record.exc_info)).rstrip("\n")
            record.exc_text = _BOT_TOKEN.sub(TOKEN_PLACEHOLDER, text)
        return True


def redact_tokens_in_logs() -> None:
    """Install the token filter on the root handlers.

    Handler filters see every record that reaches them, including those propagated from
    library loggers; a filter on a logger would only cover records logged on that logger.
    """
    for handler in logging.getLogger().handlers:
        handler.addFilter(TokenRedactingFilter())


def log(func: F) -> F:
    """Log decorator to give ENTER/EXIT logs of a function"""
    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_decorator(*args: object, **kwargs: object) -> Any:
            logger = logging.getLogger(func.__module__)
            logger.debug("ENTER: %s", func.__name__)
            result = await func(*args, **kwargs)
            logger.debug("RESULT: %s", result)
            logger.debug("EXIT: %s", func.__name__)
            return result

        return cast(F, async_decorator)

    @functools.wraps(func)
    def sync_decorator(*args: object, **kwargs: object) -> Any:
        logger = logging.getLogger(func.__module__)
        logger.debug("ENTER: %s", func.__name__)
        result = func(*args, **kwargs)
        logger.debug("RESULT: %s", result)
        logger.debug("EXIT: %s", func.__name__)
        return result

    return cast(F, sync_decorator)


def method(func: F) -> F:
    """Log decorator to give ENTER/EXIT logs of a class method"""
    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_decorator(self: object, *args: object, **kwargs: object) -> Any:
            logger = logging.getLogger(func.__module__)
            logger.debug("ENTER: %s", func.__name__)
            result = await func(self, *args, **kwargs)
            logger.debug("RESULT: %s", result)
            logger.debug("EXIT: %s", func.__name__)
            return result

        return cast(F, async_decorator)

    @functools.wraps(func)
    def sync_decorator(self: object, *args: object, **kwargs: object) -> Any:
        logger = logging.getLogger(func.__module__)
        logger.debug("ENTER: %s", func.__name__)
        result = func(self, *args, **kwargs)
        logger.debug("RESULT: %s", result)
        logger.debug("EXIT: %s", func.__name__)
        return result

    return cast(F, sync_decorator)
