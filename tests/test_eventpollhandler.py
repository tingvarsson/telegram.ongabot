import unittest
from unittest.mock import AsyncMock, MagicMock

from ongabot.handler.eventpollhandler import callback


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
        context.bot_data.get_chat.return_value.unverified = {42: "Will"}

        await callback(update, context)

        event.update_status_message.assert_awaited_once_with(context.bot, unverified={42: "Will"})


if __name__ == "__main__":
    unittest.main()
