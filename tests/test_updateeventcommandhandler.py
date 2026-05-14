import unittest
from datetime import date, time
from unittest.mock import AsyncMock, MagicMock, patch

from ongabot.handler.updateeventcommandhandler import callback


def _make_active_event(poll_id, event_date, start_time=time(18, 30), num_slots=5):
    event = MagicMock()
    event.poll_id = poll_id
    event.event_date = event_date
    event.start_time = start_time
    event.num_slots = num_slots
    event.completed = False
    return event


class UpdateEventConflictCheckTest(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_when_new_date_has_active_event(self):
        target = _make_active_event("p1", date(2026, 6, 4))
        conflicting = _make_active_event("p2", date(2026, 6, 11))
        conflicting.completed = False

        chat = MagicMock()
        chat.active_events = [target]
        chat.get_event_by_date.return_value = conflicting

        update = MagicMock()
        update.effective_chat.id = 1
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.args = ["target_date=2026-06-04", "day=2026-06-11"]
        context.bot_data.get_chat.return_value = chat

        await callback(update, context)

        update.message.reply_text.assert_called_once()
        msg = update.message.reply_text.call_args[0][0]
        self.assertIn("/cancelevent", msg)

    async def test_rejects_when_new_date_has_cancelled_event(self):
        target = _make_active_event("p1", date(2026, 6, 4))
        cancelled = MagicMock()
        cancelled.completed = True

        chat = MagicMock()
        chat.active_events = [target]
        chat.get_event_by_date.return_value = cancelled

        update = MagicMock()
        update.effective_chat.id = 1
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.args = ["target_date=2026-06-04", "day=2026-06-11"]
        context.bot_data.get_chat.return_value = chat

        await callback(update, context)

        update.message.reply_text.assert_called_once()
        msg = update.message.reply_text.call_args[0][0]
        self.assertIn("force=true", msg)

    async def test_calls_remove_event_before_create(self):
        target = _make_active_event("p1", date(2026, 6, 4))
        chat = MagicMock()
        chat.active_events = [target]
        chat.get_event_by_date.return_value = None
        chat.remove_pinned_poll = AsyncMock()

        update = MagicMock()
        update.effective_chat.id = 1
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.args = ["target_date=2026-06-04", "slots=3"]
        context.bot_data.get_chat.return_value = chat

        with patch("ongabot.handler.updateeventcommandhandler.create_event", AsyncMock()):
            await callback(update, context)

        chat.remove_event.assert_called_once_with("p1")


if __name__ == "__main__":
    unittest.main()
