import unittest
from unittest.mock import AsyncMock, MagicMock

from telegram.constants import ChatMemberStatus, ChatType
from telegram.error import TelegramError

from ongabot.utils import dm

GROUP_A = -1001234567890
GROUP_B = -1009876543210
ADMIN_DM = 4242  # a private chat a bot admin authorized
USER_ID = 7


def _member(status, is_member=None):
    member = MagicMock(spec=["status", "is_member"])
    member.status = status
    member.is_member = is_member
    return member


def _bot(statuses=None, titles=None):
    """A bot whose get_chat_member answers per chat id from statuses (a status or an exception)."""
    statuses = statuses or {}
    titles = titles or {}
    bot = MagicMock()

    async def get_chat_member(chat_id, _user_id):
        outcome = statuses.get(chat_id, _member(ChatMemberStatus.LEFT))
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def get_chat(chat_id):
        return MagicMock(title=titles.get(chat_id))

    bot.get_chat_member = AsyncMock(side_effect=get_chat_member)
    bot.get_chat = AsyncMock(side_effect=get_chat)
    return bot


def _bot_data(authorized=(GROUP_A, GROUP_B, ADMIN_DM)):
    bot_data = MagicMock()
    bot_data.authorized_chats = set(authorized)
    bot_data.is_authorized.side_effect = lambda chat_id: chat_id in bot_data.authorized_chats
    bot_data.get_chat.side_effect = lambda chat_id: f"chat:{chat_id}"
    return bot_data


def _update(private=True):
    update = MagicMock()
    update.effective_chat.type = ChatType.PRIVATE if private else ChatType.SUPERGROUP
    update.effective_chat.id = USER_ID if private else GROUP_A
    update.effective_user.id = USER_ID
    update.message.reply_text = AsyncMock()
    return update


def _context(bot, bot_data):
    context = MagicMock()
    context.bot = bot
    context.bot_data = bot_data
    return context


class IsGroupMemberTest(unittest.IsolatedAsyncioTestCase):
    async def _check(self, member):
        return await dm.is_group_member(_bot({GROUP_A: member}), GROUP_A, USER_ID)

    async def test_members_admins_and_owners_are_in(self):
        for status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            with self.subTest(status=status):
                self.assertTrue(await self._check(_member(status)))

    async def test_restricted_user_is_in_only_while_still_a_member(self):
        self.assertTrue(await self._check(_member(ChatMemberStatus.RESTRICTED, is_member=True)))
        self.assertFalse(await self._check(_member(ChatMemberStatus.RESTRICTED, is_member=False)))

    async def test_left_and_banned_users_are_out(self):
        for status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
            with self.subTest(status=status):
                self.assertFalse(await self._check(_member(status)))

    async def test_a_failed_lookup_counts_as_not_a_member(self):
        self.assertFalse(await self._check(TelegramError("chat not found")))


class CanReadGroupTest(unittest.IsolatedAsyncioTestCase):
    async def test_member_of_an_authorized_group_can_read_it(self):
        bot = _bot({GROUP_A: _member(ChatMemberStatus.MEMBER)})
        self.assertTrue(await dm.can_read_group(bot, _bot_data(), GROUP_A, USER_ID))

    async def test_a_deauthorized_group_cannot_be_read_even_by_a_member(self):
        bot = _bot({GROUP_A: _member(ChatMemberStatus.MEMBER)})
        self.assertFalse(await dm.can_read_group(bot, _bot_data(authorized=(GROUP_B,)), GROUP_A, USER_ID))

    async def test_a_private_chat_id_is_never_a_readable_group(self):
        bot = _bot({ADMIN_DM: _member(ChatMemberStatus.MEMBER)})
        self.assertFalse(await dm.can_read_group(bot, _bot_data(), ADMIN_DM, USER_ID))
        bot.get_chat_member.assert_not_awaited()


class MemberGroupIdsTest(unittest.IsolatedAsyncioTestCase):
    async def test_lists_only_authorized_groups_the_user_is_in(self):
        bot = _bot({GROUP_A: _member(ChatMemberStatus.MEMBER), GROUP_B: _member(ChatMemberStatus.LEFT)})
        self.assertEqual(await dm.member_group_ids(bot, _bot_data(), USER_ID), [GROUP_A])

    async def test_skips_authorized_private_chats(self):
        bot = _bot()
        await dm.member_group_ids(bot, _bot_data(), USER_ID)
        checked = {call.args[0] for call in bot.get_chat_member.await_args_list}
        self.assertEqual(checked, {GROUP_A, GROUP_B})

    async def test_a_group_telegram_errors_on_is_skipped_not_fatal(self):
        bot = _bot({GROUP_A: TelegramError("migrated"), GROUP_B: _member(ChatMemberStatus.MEMBER)})
        self.assertEqual(await dm.member_group_ids(bot, _bot_data(), USER_ID), [GROUP_B])


class PickDataTest(unittest.TestCase):
    def test_round_trips_with_and_without_an_arg(self):
        self.assertEqual(dm.decode_pick(dm.encode_pick("cs2", GROUP_A, "2026-09-02")), ("cs2", GROUP_A, "2026-09-02"))
        self.assertEqual(dm.decode_pick(dm.encode_pick("statistics", GROUP_A)), ("statistics", GROUP_A, ""))

    def test_longest_data_fits_telegrams_limit(self):
        data = dm.encode_pick("leaderboard", -1009999999999, "2026-12-31")
        self.assertLessEqual(len(data.encode()), dm.CALLBACK_DATA_MAX_BYTES)

    def test_rejects_malformed_data(self):
        for data in ("dm_pick", "dm_pick:cs2", "dm_pick:cs2:notanumber", "other:cs2:-1", "dm_pick::-1"):
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    dm.decode_pick(data)


class ResolveGroupTest(unittest.IsolatedAsyncioTestCase):
    async def test_in_a_group_it_is_that_group(self):
        bot, bot_data = _bot(), _bot_data()
        update = _update(private=False)

        chat = await dm.resolve_group(update, _context(bot, bot_data), "statistics")

        self.assertEqual(chat, f"chat:{GROUP_A}")
        bot.get_chat_member.assert_not_awaited()

    async def test_in_a_private_chat_with_no_group_it_says_so(self):
        update = _update()

        chat = await dm.resolve_group(update, _context(_bot(), _bot_data()), "statistics")

        self.assertIsNone(chat)
        update.message.reply_text.assert_awaited_once_with(dm.NOT_IN_ANY_GROUP)

    async def test_in_a_private_chat_with_one_group_it_is_that_group(self):
        bot = _bot({GROUP_B: _member(ChatMemberStatus.MEMBER)})
        update = _update()

        chat = await dm.resolve_group(update, _context(bot, _bot_data()), "statistics")

        self.assertEqual(chat, f"chat:{GROUP_B}")
        update.message.reply_text.assert_not_awaited()

    async def test_in_a_private_chat_with_several_groups_it_sends_a_picker(self):
        bot = _bot(
            {GROUP_A: _member(ChatMemberStatus.MEMBER), GROUP_B: _member(ChatMemberStatus.ADMINISTRATOR)},
            titles={GROUP_A: "ONGA", GROUP_B: None},
        )
        update = _update()

        chat = await dm.resolve_group(update, _context(bot, _bot_data()), "cs2", "2026-09-02")

        self.assertIsNone(chat)
        self.assertEqual(update.message.reply_text.await_args.args, (dm.PICK_GROUP_PROMPT,))
        keyboard = update.message.reply_text.await_args.kwargs["reply_markup"].inline_keyboard
        buttons = [row[0] for row in keyboard]
        # In chat id order. A group without a title falls back to its id rather than an empty button.
        self.assertEqual([b.text for b in buttons], [str(GROUP_B), "ONGA"])
        self.assertEqual(
            [b.callback_data for b in buttons],
            [f"dm_pick:cs2:{GROUP_B}:2026-09-02", f"dm_pick:cs2:{GROUP_A}:2026-09-02"],
        )


class GroupTitleTest(unittest.IsolatedAsyncioTestCase):
    async def test_falls_back_to_the_id_when_telegram_errors(self):
        bot = MagicMock()
        bot.get_chat = AsyncMock(side_effect=TelegramError("chat not found"))
        self.assertEqual(await dm.group_title(bot, GROUP_A), str(GROUP_A))


if __name__ == "__main__":
    unittest.main()
