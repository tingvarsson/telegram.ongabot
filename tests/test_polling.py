import unittest
from unittest.mock import AsyncMock, patch

from telegram.request import HTTPXRequest

from ongabot.utils.polling import PollTracker, PollTrackingRequest


class PollTrackerTest(unittest.TestCase):
    def test_nothing_recorded_yet(self):
        self.assertIsNone(PollTracker().seconds_since_success())

    def test_seconds_since_the_last_success(self):
        tracker = PollTracker()
        with patch("ongabot.utils.polling.time.monotonic", return_value=100.0):
            tracker.record_success()
        with patch("ongabot.utils.polling.time.monotonic", return_value=142.5):
            self.assertEqual(tracker.seconds_since_success(), 42.5)


class PollTrackingRequestTest(unittest.IsolatedAsyncioTestCase):
    async def _answer(self, code):
        tracker = PollTracker()
        request = PollTrackingRequest(tracker)
        with patch.object(HTTPXRequest, "do_request", AsyncMock(return_value=(code, b"{}"))) as sent:
            result = await request.do_request("https://api.telegram.org/getUpdates", "POST", read_timeout=15)
        sent.assert_awaited_once_with("https://api.telegram.org/getUpdates", "POST", read_timeout=15)
        self.assertEqual(result, (code, b"{}"))
        return tracker

    async def test_a_successful_answer_is_recorded(self):
        tracker = await self._answer(200)
        self.assertIsNotNone(tracker.seconds_since_success())

    async def test_an_error_answer_is_not_recorded(self):
        # 409: another instance is polling the same token - this one gets no updates.
        for code in (401, 409, 502):
            with self.subTest(code=code):
                tracker = await self._answer(code)
                self.assertIsNone(tracker.seconds_since_success())

    def test_uses_a_single_connection_like_the_builder_default(self):
        request = PollTrackingRequest(PollTracker())
        # pylint: disable=protected-access
        self.assertEqual(request._client_kwargs["limits"].max_connections, 1)


if __name__ == "__main__":
    unittest.main()
