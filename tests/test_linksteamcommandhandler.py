import unittest
from unittest.mock import AsyncMock, MagicMock

from ongabot.handler.linksteamcommandhandler import callback as link_callback
from ongabot.handler.unlinksteamcommandhandler import callback as unlink_callback
from ongabot.userdata import UserData

VALID = "76561198034202275"


def _update_context(args):
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_user.id = 11

    context = MagicMock()
    context.args = args
    context.user_data = UserData()

    return update, context


def _reply(update):
    return update.message.reply_text.await_args.args[0]


class LinkSteamTest(unittest.IsolatedAsyncioTestCase):
    async def test_stores_a_valid_steam64(self):
        update, context = _update_context([VALID])

        await link_callback(update, context)

        self.assertEqual(context.user_data.steam64_id, VALID)

    async def test_stores_a_steam64_from_a_profile_url(self):
        update, context = _update_context([f"https://steamcommunity.com/profiles/{VALID}"])

        await link_callback(update, context)

        self.assertEqual(context.user_data.steam64_id, VALID)

    async def test_confirms_the_link_to_the_user(self):
        update, context = _update_context([VALID])

        await link_callback(update, context)

        self.assertIn(VALID, _reply(update))

    async def test_rejects_a_vanity_url_and_explains_why(self):
        update, context = _update_context(["https://steamcommunity.com/id/someone"])

        await link_callback(update, context)

        self.assertIsNone(context.user_data.steam64_id)
        self.assertIn("/profiles/", _reply(update))

    async def test_rejects_garbage_without_storing_anything(self):
        update, context = _update_context(["nonsense"])

        await link_callback(update, context)

        self.assertIsNone(context.user_data.steam64_id)

    async def test_shows_usage_when_called_without_an_argument(self):
        update, context = _update_context([])

        await link_callback(update, context)

        self.assertIsNone(context.user_data.steam64_id)
        self.assertIn("/linksteam", _reply(update))

    async def test_relinking_replaces_the_previous_account(self):
        update, context = _update_context([VALID])
        context.user_data.set_steam64_id("76561198000000001")

        await link_callback(update, context)

        self.assertEqual(context.user_data.steam64_id, VALID)


class UnlinkSteamTest(unittest.IsolatedAsyncioTestCase):
    async def test_clears_an_existing_link(self):
        update, context = _update_context([])
        context.user_data.set_steam64_id(VALID)

        await unlink_callback(update, context)

        self.assertIsNone(context.user_data.steam64_id)

    async def test_is_harmless_when_nothing_was_linked(self):
        update, context = _update_context([])

        await unlink_callback(update, context)

        self.assertIsNone(context.user_data.steam64_id)
        update.message.reply_text.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
