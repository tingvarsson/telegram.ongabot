import unittest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from ongabot.chat import Chat
from ongabot.handler.neweventcommandhandler import _parse_args, callback

# A Sunday; the default event day, wednesday, is three days later.
TODAY = date(2026, 10, 4)


class NewEventForceArgTest(unittest.TestCase):
    def test_force_true_parsed(self):
        data, force = _parse_args(["force=true"], TODAY)
        self.assertTrue(force)

    def test_force_false_parsed(self):
        data, force = _parse_args(["force=false"], TODAY)
        self.assertFalse(force)

    def test_force_defaults_to_false(self):
        data, force = _parse_args([], TODAY)
        self.assertFalse(force)

    def test_force_with_other_args(self):
        data, force = _parse_args(["day=friday", "force=true"], TODAY)
        self.assertTrue(force)


class NewEventDateArgTest(unittest.TestCase):
    def test_defaults_to_the_coming_wednesday_from_today(self):
        data, _ = _parse_args([], TODAY)
        self.assertEqual(data.event_date, date(2026, 10, 7))

    def test_weekday_counts_from_today(self):
        data, _ = _parse_args(["day=friday"], TODAY)
        self.assertEqual(data.event_date, date(2026, 10, 9))


class NewEventForcePassthroughTest(unittest.IsolatedAsyncioTestCase):
    async def test_force_true_passed_to_create_event(self):
        update = MagicMock()
        update.message = MagicMock()
        update.effective_chat.id = 42
        context = MagicMock()
        context.args = ["force=true"]
        context.bot_data.get_chat.return_value = Chat(42)

        mock_create = AsyncMock(return_value=None)
        with patch("ongabot.handler.neweventcommandhandler.create_event", mock_create):
            await callback(update, context)

        mock_create.assert_called_once()
        _call_kwargs = mock_create.call_args[1]
        self.assertTrue(_call_kwargs.get("force", False))


if __name__ == "__main__":
    unittest.main()
