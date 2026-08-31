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


class UpdateEventMultipleCandidatesTest(unittest.IsolatedAsyncioTestCase):
    """Without target_date, every active event is a candidate and none may be updated."""

    async def _run_with_two_active_events(self):
        # Passed out of chronological order to prove the listing is sorted, not incidental.
        later = _make_active_event("p2", date(2026, 6, 11), time(20, 0))
        earlier = _make_active_event("p1", date(2026, 6, 4), time(18, 30))

        chat = MagicMock()
        chat.active_events = [later, earlier]
        chat.get_event_by_date.return_value = None
        chat.remove_pinned_poll = AsyncMock()

        update = MagicMock()
        update.effective_chat.id = 1
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        context.args = ["slots=3"]
        context.bot_data.get_chat.return_value = chat

        with patch("ongabot.handler.updateeventcommandhandler.create_event", AsyncMock()) as create:
            await callback(update, context)
        return update, chat, create, earlier, later

    async def test_lists_every_candidate_in_chronological_order(self):
        update, _, _, earlier, later = await self._run_with_two_active_events()

        update.message.reply_text.assert_called_once()
        msg = update.message.reply_text.call_args[0][0]
        self.assertIn("Multiple active events match", msg)
        self.assertIn("target_date=", msg)
        self.assertIn(str(earlier.event_date), msg)
        self.assertIn(str(later.event_date), msg)
        self.assertIn("18:30", msg)
        self.assertIn("20:00", msg)
        self.assertLess(msg.index(str(earlier.event_date)), msg.index(str(later.event_date)))

    async def test_updates_nothing_while_the_choice_is_ambiguous(self):
        _, chat, create, _, _ = await self._run_with_two_active_events()

        chat.remove_event.assert_not_called()
        create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
