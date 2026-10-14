import unittest
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.error import TelegramError

from ongabot.chat import Chat
from ongabot.event import Event
from ongabot.handler.eventpollhandler import callback
from tests import message_fixtures


class EventPollCallbackNoneEventTest(unittest.IsolatedAsyncioTestCase):
    async def test_returns_early_when_event_is_none(self):
        update = MagicMock()
        update.poll.id = "unknown_poll_id"
        context = MagicMock()
        context.bot_data.get_event.return_value = None

        await callback(update, context)

        context.bot_data.get_event.assert_called_once_with("unknown_poll_id")
        context.bot.send_message.assert_not_called()

    async def test_verification_poll_is_ignored_without_an_error(self):
        update = MagicMock()
        update.poll.id = "vote1"
        context = MagicMock()
        context.bot_data.get_event.return_value = None
        context.bot_data.is_verification_poll.return_value = True

        with self.assertNoLogs(level="ERROR"):
            await callback(update, context)

        context.bot_data.is_verification_poll.assert_called_once_with("vote1")


class EventPollCallbackUnverifiedBadgeTest(unittest.IsolatedAsyncioTestCase):
    async def test_status_message_gets_the_chats_unverified_members(self):
        update = MagicMock()
        context = MagicMock()
        event = context.bot_data.get_event.return_value
        event.update_status_message = AsyncMock()
        event.claim_stack_celebration.return_value = None
        context.bot_data.get_chat.return_value.unverified = {42: "Will"}

        await callback(update, context)

        event.update_status_message.assert_awaited_once_with(context.bot, unverified={42: "Will"})


def _open_event(slot_votes, event_date=None):
    """An open event with slot_votes votes on each of its time slots, a week ahead by default
    so it has not started yet."""
    event = message_fixtures.event(event_date or date.today() + timedelta(weeks=1), [], [])
    event.completed = False
    for option, votes in zip(event.poll.options, slot_votes):
        option.voter_count = votes
    event.update_status_message = AsyncMock()
    return event


class EventPollStackCelebrationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.chat = Chat(message_fixtures.CHAT_ID)
        # The handler sees the top-level gifs module (pythonpath is ongabot/).
        patcher = patch("gifs.moments.send_with_gif", AsyncMock())
        self.send = patcher.start()
        self.addCleanup(patcher.stop)

    def _context(self, event):
        context = MagicMock()
        context.bot_data.get_event.return_value = event
        context.bot_data.get_chat.return_value = self.chat
        return context

    async def _vote(self, event):
        update = MagicMock()
        update.poll = event.poll
        await callback(update, self._context(event))

    async def test_a_slot_reaching_five_is_celebrated_once(self):
        event = _open_event([3, 5, 2])
        self.chat.pinned_polls[event.poll_id] = MagicMock(message_id=77)

        with self.assertLogs("gifs.moments", level="INFO"):
            await self._vote(event)
        await self._vote(event)

        self.send.assert_awaited_once()
        self.assertEqual(self.send.call_args.args[2], "🎉 Five-stack at 19.10!")
        self.assertEqual(self.send.call_args.kwargs["reply_parameters"].message_id, 77)
        self.assertTrue(event.stack_celebrated)
        event.update_status_message.assert_awaited()

    async def test_dropping_below_and_back_is_not_celebrated_again(self):
        event = _open_event([5, 0, 0])
        await self._vote(event)
        event.poll.options[0].voter_count = 4
        await self._vote(event)
        event.poll.options[0].voter_count = 5
        await self._vote(event)

        self.send.assert_awaited_once()

    async def test_four_is_not_a_stack(self):
        await self._vote(_open_event([4, 4, 4]))
        self.send.assert_not_awaited()

    async def test_a_closed_event_is_not_celebrated(self):
        for flag in ("completed", "cancelled"):
            with self.subTest(flag=flag):
                event = _open_event([5, 0, 0])
                setattr(event, flag, True)
                await self._vote(event)
                self.send.assert_not_awaited()
                self.assertFalse(event.stack_celebrated)

    async def test_a_stack_filling_up_after_the_start_is_no_news(self):
        """A fifth tick at 23:00, say to keep a played streak, does not celebrate the 19.10 slot."""
        event = _open_event([5, 0, 0], event_date=date.today() - timedelta(days=1))

        await self._vote(event)

        self.send.assert_not_awaited()
        self.assertFalse(event.stack_celebrated)

    async def test_a_failed_celebration_is_retried_on_the_next_vote(self):
        event = _open_event([5, 0, 0])
        self.send.side_effect = [TelegramError("flood"), None]

        with self.assertLogs("ongabot.handler.eventpollhandler", level="WARNING"):
            await self._vote(event)
        self.assertFalse(event.stack_celebrated)
        # The status message is still brought up to date.
        event.update_status_message.assert_awaited_once()

        await self._vote(event)
        self.assertEqual(self.send.await_count, 2)
        self.assertTrue(event.stack_celebrated)


class EventStackCelebratedMigrationTest(unittest.TestCase):
    def _restored(self, slot_votes):
        event = _open_event(slot_votes)
        state = dict(event.__dict__)
        del state["stack_celebrated"]
        restored = Event.__new__(Event)
        restored.__setstate__(state)
        return restored

    def test_an_old_event_short_of_a_stack_can_still_be_celebrated(self):
        self.assertFalse(self._restored([4, 0, 0]).stack_celebrated)

    def test_an_old_event_with_a_full_stack_is_not_celebrated_after_the_fact(self):
        self.assertTrue(self._restored([5, 0, 0]).stack_celebrated)


if __name__ == "__main__":
    unittest.main()
