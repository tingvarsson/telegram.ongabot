import unittest
from datetime import date, time
from unittest.mock import AsyncMock, MagicMock

from ongabot.handler.canceleventcommandhandler import callback


def _make_active_event(poll_id, event_date, start_time=time(18, 30)):
    event = MagicMock()
    event.poll_id = poll_id
    event.event_date = event_date
    event.start_time = start_time
    event.completed = False
    event.cancelled = False
    return event


class CancelEventMultipleCandidatesTest(unittest.IsolatedAsyncioTestCase):
    """Without target_date, every active event is a candidate and none may be cancelled."""

    async def _run_with_two_active_events(self):
        # Passed out of chronological order to prove the listing is sorted, not incidental.
        later = _make_active_event("p2", date(2026, 6, 11), time(20, 0))
        earlier = _make_active_event("p1", date(2026, 6, 4), time(18, 30))

        chat = MagicMock()
        chat.active_events = [later, earlier]
        chat.remove_pinned_poll = AsyncMock()

        update = MagicMock()
        update.effective_chat.id = 1
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.args = []
        context.bot_data.get_chat.return_value = chat
        context.bot.send_message = AsyncMock()

        await callback(update, context)
        return context, earlier, later

    async def test_lists_every_candidate_in_chronological_order(self):
        context, earlier, later = await self._run_with_two_active_events()

        context.bot.send_message.assert_called_once()
        msg = context.bot.send_message.call_args[0][1]
        self.assertIn("Multiple active events match", msg)
        self.assertIn("target_date=", msg)
        self.assertIn(str(earlier.event_date), msg)
        self.assertIn(str(later.event_date), msg)
        self.assertIn("18:30", msg)
        self.assertIn("20:00", msg)
        self.assertLess(msg.index(str(earlier.event_date)), msg.index(str(later.event_date)))

    async def test_cancels_nothing_while_the_choice_is_ambiguous(self):
        _, earlier, later = await self._run_with_two_active_events()

        for event in (earlier, later):
            self.assertFalse(event.cancelled)
            event.mark_complete.assert_not_called()


class CancelEventSuccessMessageTest(unittest.IsolatedAsyncioTestCase):
    async def test_success_message_includes_event_date(self):
        target_date = date(2026, 6, 4)
        event = MagicMock()
        event.event_date = target_date
        event.poll_id = "p1"
        event.completed = False

        chat = MagicMock()
        chat.active_events = [event]
        chat.remove_pinned_poll = AsyncMock()

        update = MagicMock()
        update.effective_chat.id = 1
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.args = []
        context.bot_data.get_chat.return_value = chat
        context.bot.send_message = AsyncMock()

        await callback(update, context)

        context.bot.send_message.assert_called_once()
        msg = context.bot.send_message.call_args[0][1]
        self.assertIn(str(target_date), msg)
        self.assertIn("cancelled", msg.lower())


if __name__ == "__main__":
    unittest.main()
