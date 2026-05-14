import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from ongabot.handler.neweventcommandhandler import _parse_args, callback


class NewEventForceArgTest(unittest.TestCase):
    def test_force_true_parsed(self):
        data, force = _parse_args(["force=true"])
        self.assertTrue(force)

    def test_force_false_parsed(self):
        data, force = _parse_args(["force=false"])
        self.assertFalse(force)

    def test_force_defaults_to_false(self):
        data, force = _parse_args([])
        self.assertFalse(force)

    def test_force_with_other_args(self):
        data, force = _parse_args(["day=friday", "force=true"])
        self.assertTrue(force)


class NewEventForcePassthroughTest(unittest.IsolatedAsyncioTestCase):
    async def test_force_true_passed_to_create_event(self):
        update = MagicMock()
        update.message = MagicMock()
        update.effective_chat.id = 42
        context = MagicMock()
        context.args = ["force=true"]

        mock_create = AsyncMock(return_value=None)
        with patch("ongabot.handler.neweventcommandhandler.create_event", mock_create):
            await callback(update, context)

        mock_create.assert_called_once()
        _call_kwargs = mock_create.call_args[1]
        self.assertTrue(_call_kwargs.get("force", False))


if __name__ == "__main__":
    unittest.main()
