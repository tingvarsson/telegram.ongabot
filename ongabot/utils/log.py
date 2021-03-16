"""This module contains log decorator."""
import functools
import logging
from typing import Any, Callable, TypeVar, cast


F = TypeVar("F", bound=Callable[..., Any])  # pylint: disable=invalid-name


def log(func: F) -> F:
    """Log decorator to give ENTER/EXIT logs"""

    @functools.wraps(func)
    def decorator(*args: object, **kwargs: object) -> Any:
        logger = logging.getLogger(func.__module__)
        logger.debug("ENTER: %s", func.__name__)
        result = func(*args, **kwargs)
        logger.debug(result)
        logger.debug("EXIT: %s", func.__name__)
        return result

    return cast(F, decorator)
