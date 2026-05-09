"""This module contains log decorator."""

import functools
import inspect
import logging
from typing import Any, Callable, TypeVar, cast

F = TypeVar("F", bound=Callable[..., Any])  # pylint: disable=invalid-name


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
