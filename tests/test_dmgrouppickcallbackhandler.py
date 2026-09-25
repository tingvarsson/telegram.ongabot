import re
import unittest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import InaccessibleMessage, Message
from telegram.constants import ChatType

from ongabot.handler import dmgrouppickcallbackhandler as handler
from ongabot.utils.dm import GROUP_UNAVAILABLE

GROUP_ID = -100123
USER_ID = 7
MODULE = "ongabot.handler.dmgrouppickcallbackhandler"


def _make(data):
    update = MagicMock()
    update.effective_user.id = USER_ID
    update.effective_chat.type = ChatType.PRIVATE
    query = update.callback_query
    query.data = data
    query.message = MagicMock(spec=Message)
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()

    context = MagicMock()
    context.bot_data.get_chat.return_value = "CHAT"
    return update, context


class CallbackPatternTest(unittest.TestCase):
    def test_matches_picker_data_only(self):
        self.assertIsNotNone(re.match(handler.CALLBACK_PATTERN, f"dm_pick:cs2:{GROUP_ID}"))
        self.assertIsNone(re.match(handler.CALLBACK_PATTERN, "stats_sort:played"))

    def test_every_picker_command_has_a_sender(self):
        self.assertEqual(set(handler.SENDERS), {"statistics", "leaderboard", "topics", "cs2"})


class DmGroupPickCallbackTest(unittest.IsolatedAsyncioTestCase):
    async def _run(self, data, can_read=True, title="ONGA"):
        update, context = _make(data)
        with (
            patch(f"{MODULE}.can_read_group", AsyncMock(return_value=can_read)) as can_read_group,
            patch(f"{MODULE}.group_title", AsyncMock(return_value=title)),
            patch(f"{MODULE}.send_statistics", AsyncMock()) as statistics,
            patch(f"{MODULE}.send_leaderboard", AsyncMock()) as leaderboard,
            patch(f"{MODULE}.send_topics", AsyncMock()) as topics,
            patch(f"{MODULE}.send_cs2", AsyncMock()) as cs2,
        ):
            await handler.callback(update, context)
        senders = {"statistics": statistics, "leaderboard": leaderboard, "topics": topics, "cs2": cs2}
        return update, context, can_read_group, senders

    async def test_answers_each_command_for_the_picked_group(self):
        for command in ("statistics", "leaderboard", "topics"):
            with self.subTest(command=command):
                update, context, _, senders = await self._run(f"dm_pick:{command}:{GROUP_ID}")

                context.bot_data.get_chat.assert_called_once_with(GROUP_ID)
                senders[command].assert_awaited_once_with(update.callback_query.message, "CHAT")
                for other, sender in senders.items():
                    if other != command:
                        sender.assert_not_awaited()

    async def test_cs2_gets_the_date_the_picker_carried(self):
        update, context, _, senders = await self._run(f"dm_pick:cs2:{GROUP_ID}:2026-09-02")
        senders["cs2"].assert_awaited_once_with(update.callback_query.message, context, "CHAT", date(2026, 9, 2))

    async def test_cs2_without_a_date_reports_the_latest_event(self):
        update, context, _, senders = await self._run(f"dm_pick:cs2:{GROUP_ID}")
        senders["cs2"].assert_awaited_once_with(update.callback_query.message, context, "CHAT", None)

    async def test_replaces_the_picker_with_the_group_title(self):
        update, _, _, _ = await self._run(f"dm_pick:statistics:{GROUP_ID}", title="ONGA")
        update.callback_query.answer.assert_awaited_once_with()
        update.callback_query.edit_message_text.assert_awaited_once_with("ONGA")

    async def test_rechecks_the_tapper_may_read_the_group(self):
        _, context, can_read_group, _ = await self._run(f"dm_pick:statistics:{GROUP_ID}")
        can_read_group.assert_awaited_once_with(context.bot, context.bot_data, GROUP_ID, USER_ID)

    async def test_refuses_a_user_no_longer_in_the_group(self):
        update, context, _, senders = await self._run(f"dm_pick:statistics:{GROUP_ID}", can_read=False)

        update.callback_query.edit_message_text.assert_awaited_once_with(GROUP_UNAVAILABLE)
        context.bot_data.get_chat.assert_not_called()
        senders["statistics"].assert_not_awaited()

    async def test_a_tap_outside_a_private_chat_is_answered_and_ignored(self):
        """Pickers only exist in private chats; forged data in a group must not post another group there."""
        update, context = _make(f"dm_pick:statistics:{GROUP_ID}")
        update.effective_chat.type = ChatType.SUPERGROUP

        with patch(f"{MODULE}.can_read_group", AsyncMock()) as can_read_group:
            await handler.callback(update, context)

        update.callback_query.answer.assert_awaited_once_with()
        can_read_group.assert_not_awaited()
        context.bot_data.get_chat.assert_not_called()

    async def test_unknown_command_or_bad_data_is_answered_and_ignored(self):
        for data in (f"dm_pick:newevent:{GROUP_ID}", "dm_pick:statistics:nope", f"dm_pick:cs2:{GROUP_ID}:garbage"):
            with self.subTest(data=data):
                update, context, can_read_group, _ = await self._run(data)

                update.callback_query.answer.assert_awaited_once_with()
                can_read_group.assert_not_awaited()
                context.bot_data.get_chat.assert_not_called()

    async def test_a_tap_on_an_inaccessible_picker_is_answered_and_ignored(self):
        update, context = _make(f"dm_pick:statistics:{GROUP_ID}")
        update.callback_query.message = MagicMock(spec=InaccessibleMessage)

        with patch(f"{MODULE}.can_read_group", AsyncMock()) as can_read_group:
            await handler.callback(update, context)

        update.callback_query.answer.assert_awaited_once_with()
        can_read_group.assert_not_awaited()

    async def test_missing_query_data_is_a_noop(self):
        update, context, can_read_group, _ = await self._run(None)
        update.callback_query.answer.assert_not_awaited()
        can_read_group.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
