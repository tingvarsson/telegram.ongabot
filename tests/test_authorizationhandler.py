import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.constants import ChatType
from telegram.ext import ApplicationHandlerStop

from ongabot.handler.authorizationhandler import NOT_ENABLED, PRIVATE_CHAT_HINT, callback

GROUP_ID = -100123
USER_ID = 7


def _update(text=None, callback_data=None, private=False):
    update = MagicMock()
    update.effective_chat.id = USER_ID if private else GROUP_ID
    update.effective_chat.type = ChatType.PRIVATE if private else ChatType.SUPERGROUP
    update.effective_user.id = USER_ID
    update.effective_message.text = text
    update.effective_message.reply_text = AsyncMock()
    if callback_data is None:
        update.callback_query = None
    else:
        update.callback_query.data = callback_data
    return update


def _context(authorized=()):
    context = MagicMock()
    context.bot_data.is_authorized.side_effect = lambda chat_id: chat_id in authorized
    return context


class AuthorizationHandlerTest(unittest.IsolatedAsyncioTestCase):
    async def _assert_passes(self, update, context):
        await callback(update, context)  # must not raise ApplicationHandlerStop
        update.effective_message.reply_text.assert_not_awaited()

    async def _assert_blocked_with(self, update, context, reply):
        with self.assertRaises(ApplicationHandlerStop):
            await callback(update, context)
        update.effective_message.reply_text.assert_awaited_once_with(reply)

    async def test_authorized_group_passes(self):
        await self._assert_passes(_update("/newevent"), _context(authorized={GROUP_ID}))

    async def test_unauthorized_group_is_blocked(self):
        await self._assert_blocked_with(_update("/statistics"), _context(), NOT_ENABLED)

    async def test_update_without_chat_passes(self):
        update = _update()
        update.effective_chat = None
        await callback(update, _context())

    async def test_bot_admin_can_authorize_an_unauthorized_group(self):
        with patch("ongabot.handler.authorizationhandler.get_bot_admins", return_value={USER_ID}):
            await self._assert_passes(_update("/authorize@ONGAbot"), _context())

    async def test_non_admin_cannot_authorize(self):
        with patch("ongabot.handler.authorizationhandler.get_bot_admins", return_value=set()):
            await self._assert_blocked_with(_update("/authorize"), _context(), NOT_ENABLED)

    async def test_private_commands_pass_in_a_private_chat(self):
        for command in ("/start", "/help", "/statistics", "/leaderboard", "/cs2 2026-09-02", "/topics", "/linksteam"):
            with self.subTest(command=command):
                await self._assert_passes(_update(command, private=True), _context())

    async def test_private_command_with_bot_name_passes_in_a_private_chat(self):
        await self._assert_passes(_update("/Statistics@ONGAbot", private=True), _context())

    async def test_group_only_command_in_a_private_chat_gets_the_hint(self):
        await self._assert_blocked_with(_update("/newevent", private=True), _context(), PRIVATE_CHAT_HINT)

    async def test_plain_text_in_a_private_chat_gets_the_hint(self):
        await self._assert_blocked_with(_update("hello", private=True), _context(), PRIVATE_CHAT_HINT)

    async def test_group_picker_and_sort_buttons_pass_in_a_private_chat(self):
        for data in ("dm_pick:statistics:-100123", "stats_sort:played:-100123"):
            with self.subTest(data=data):
                await self._assert_passes(_update(callback_data=data, private=True), _context())

    async def test_other_buttons_are_blocked_in_a_private_chat(self):
        update = _update(callback_data="other:thing", private=True)
        await self._assert_blocked_with(update, _context(), PRIVATE_CHAT_HINT)

    async def test_an_authorized_private_chat_is_unaffected(self):
        await self._assert_passes(_update("/newevent", private=True), _context(authorized={USER_ID}))

    def test_hint_lists_the_private_commands(self):
        for command in ("/help", "/statistics", "/leaderboard", "/cs2", "/topics", "/linksteam", "/unlinksteam"):
            self.assertIn(command, PRIVATE_CHAT_HINT)
        self.assertNotIn("/newevent", PRIVATE_CHAT_HINT)


if __name__ == "__main__":
    unittest.main()
