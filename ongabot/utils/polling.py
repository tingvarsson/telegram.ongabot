"""Tracks whether the bot's getUpdates long-poll is still getting answers from Telegram."""

import time
from typing import Any, Optional, Tuple

from telegram.request import HTTPXRequest


class PollTracker:
    """When Telegram last answered getUpdates successfully.

    `Updater.running` stays True even after the polling task has died (nothing watches that
    task), so it cannot tell a working bot from one that silently stopped fetching updates. A
    getUpdates answer can: Telegram holds each long-poll for at most its timeout before
    answering, so a live poller succeeds every few seconds. A dead polling task, a lost
    network, a revoked token (401) or a second instance polling the same token (409) all stop
    the successes.
    """

    def __init__(self) -> None:
        self._last_success: Optional[float] = None  # time.monotonic()

    def record_success(self) -> None:
        """Note that Telegram just answered getUpdates."""
        self._last_success = time.monotonic()

    def seconds_since_success(self) -> Optional[float]:
        """Seconds since Telegram last answered getUpdates successfully; None if it never has."""
        if self._last_success is None:
            return None
        return time.monotonic() - self._last_success


class PollTrackingRequest(HTTPXRequest):
    """The request the bot sends getUpdates through, reporting each success to a PollTracker."""

    def __init__(self, tracker: PollTracker) -> None:
        # Pool of one, matching what ApplicationBuilder builds for getUpdates by default.
        super().__init__(connection_pool_size=1)
        self._tracker = tracker

    async def do_request(self, *args: Any, **kwargs: Any) -> Tuple[int, bytes]:
        """See HTTPXRequest.do_request; additionally records a successful answer."""
        code, payload = await super().do_request(*args, **kwargs)
        # Error statuses come back here too; PTB raises on them later, in its own wrapper.
        if 200 <= code < 300:
            self._tracker.record_success()
        return code, payload
