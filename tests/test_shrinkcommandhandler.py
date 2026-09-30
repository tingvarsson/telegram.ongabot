import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.constants import ChatType

from ongabot.handler.shrinkcommandhandler import callback
from ongabot.utils.commands import SHRINK

MODULE = "ongabot.handler.shrinkcommandhandler"


def _make(args=None, reply_from=None, chat_type=ChatType.SUPERGROUP):
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_chat.id = -100123
    update.effective_chat.type = chat_type
    update.effective_user.id = 7
    if reply_from is None:
        update.message.reply_to_message = None
    else:
        update.message.reply_to_message.from_user = reply_from
        update.message.reply_to_message.forum_topic_created = None

    context = MagicMock()
    context.args = args or []
    chat = MagicMock()
    chat.chat_id = -100123
    context.bot_data.get_chat.return_value = chat
    return update, context, chat


class ShrinkCommandHandlerTest(unittest.IsolatedAsyncioTestCase):
    async def _run(self, update, context):
        with patch(f"{MODULE}.render_shrink_message", return_value="SESSION") as render:
            await callback(update, context)
        return render

    async def test_diagnoses_the_sender_by_default(self):
        update, context, chat = _make()

        render = await self._run(update, context)

        render.assert_called_once_with(chat, user=update.effective_user, username=None)
        update.message.reply_text.assert_awaited_once_with("SESSION")

    async def test_diagnoses_the_user_replied_to(self):
        patient = MagicMock()
        update, context, chat = _make(reply_from=patient)

        render = await self._run(update, context)

        render.assert_called_once_with(chat, user=patient, username=None)

    async def test_a_forum_topic_root_is_not_a_reply(self):
        update, context, chat = _make(reply_from=MagicMock())
        update.message.reply_to_message.forum_topic_created = MagicMock()

        render = await self._run(update, context)

        render.assert_called_once_with(chat, user=update.effective_user, username=None)

    async def test_diagnoses_an_at_username(self):
        update, context, chat = _make(args=["@alice"], reply_from=MagicMock())

        render = await self._run(update, context)

        render.assert_called_once_with(chat, user=None, username="alice")

    async def test_bad_args_reply_with_usage(self):
        for args in (["alice"], ["@"], ["@alice", "@bob"]):
            with self.subTest(args=args):
                update, context, _chat = _make(args=args)

                render = await self._run(update, context)

                render.assert_not_called()
                update.message.reply_text.assert_awaited_once_with(SHRINK.usage)

    async def test_a_private_chat_always_diagnoses_the_sender(self):
        update, context, chat = _make(args=["@alice"], reply_from=MagicMock(), chat_type=ChatType.PRIVATE)

        with patch(f"{MODULE}.resolve_group", AsyncMock(return_value=chat)):
            render = await self._run(update, context)

        render.assert_called_once_with(chat, user=update.effective_user, username=None)

    async def test_waits_for_a_group_pick_when_none_resolved(self):
        update, context, _chat = _make(chat_type=ChatType.PRIVATE)

        with patch(f"{MODULE}.resolve_group", AsyncMock(return_value=None)) as resolve:
            render = await self._run(update, context)

        self.assertEqual(resolve.await_args.args[2], "shrink")
        render.assert_not_called()
        update.message.reply_text.assert_not_awaited()

    async def test_no_effective_user_is_a_noop(self):
        update, context, _chat = _make()
        update.effective_user = None

        render = await self._run(update, context)

        render.assert_not_called()
        update.message.reply_text.assert_not_awaited()

    async def test_no_message_is_a_noop(self):
        update, context, _chat = _make()
        update.message = None

        render = await self._run(update, context)

        render.assert_not_called()


if __name__ == "__main__":
    unittest.main()
