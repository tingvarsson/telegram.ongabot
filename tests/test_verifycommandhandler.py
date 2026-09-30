import unittest
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from telegram import MessageEntity, User
from telegram.constants import ChatType

from ongabot.botdata import BotData
from ongabot.handler.verifycommandhandler import resolve_target, unverify_callback, verify_callback
from ongabot.utils.commands import UNVERIFY
from ongabot.verification import VerificationVote

WILL = User(id=42, first_name="Will", is_bot=False, username="william")


def _message(reply_from=None, entities=None):
    message = MagicMock()
    if reply_from is None:
        message.reply_to_message = None
    else:
        message.reply_to_message.from_user = reply_from
        message.reply_to_message.forum_topic_created = None
    message.parse_entities.return_value = entities or {}
    message.reply_text = AsyncMock()
    return message


class ResolveTargetTest(unittest.TestCase):
    def setUp(self):
        self.chat = BotData().get_chat(1)

    def test_reply_targets_the_replied_to_author(self):
        self.assertEqual(resolve_target(_message(reply_from=WILL), self.chat), WILL)

    def test_the_forum_topic_root_is_not_a_target(self):
        message = _message(reply_from=User(id=1, first_name="Topic starter", is_bot=False))
        message.reply_to_message.forum_topic_created = MagicMock()

        self.assertIsNone(resolve_target(message, self.chat))

    def test_text_mention_targets_its_user(self):
        entity = MessageEntity(MessageEntity.TEXT_MENTION, 10, 4, user=WILL)

        self.assertEqual(resolve_target(_message(entities={entity: "Will"}), self.chat), WILL)

    def test_at_mention_of_a_known_voter(self):
        event = MagicMock()
        event.poll_answers = {WILL: MagicMock()}
        self.chat.events[date(2026, 9, 2)] = event
        entity = MessageEntity(MessageEntity.MENTION, 10, 8)

        self.assertEqual(resolve_target(_message(entities={entity: "@William"}), self.chat), WILL)

    def test_at_mention_of_an_unknown_member_is_none(self):
        entity = MessageEntity(MessageEntity.MENTION, 10, 8)

        self.assertIsNone(resolve_target(_message(entities={entity: "@william"}), self.chat))


class VerifyCallbackTest(unittest.IsolatedAsyncioTestCase):
    def _run(self, message, chat_type=ChatType.GROUP):
        update = MagicMock()
        update.message = message
        update.effective_chat.id = 1
        update.effective_chat.type = chat_type
        self.bot_data = BotData()
        self.chat = self.bot_data.get_chat(1)
        context = MagicMock()
        context.bot_data = self.bot_data
        poll_message = MagicMock(message_id=100)
        poll_message.poll.id = "vote1"
        context.bot.send_poll = AsyncMock(return_value=poll_message)
        self.context = context
        return update, context

    def _reply(self, message):
        return message.reply_text.call_args.args[0]

    async def test_unverify_by_reply_starts_a_vote(self):
        message = _message(reply_from=WILL)
        update, context = self._run(message)

        await unverify_callback(update, context)

        context.bot.send_poll.assert_awaited_once()
        self.assertEqual(self.chat.open_vote_for(42).poll_id, "vote1")
        context.job_queue.run_once.assert_called_once()
        message.reply_text.assert_not_called()

    async def test_no_target_replies_with_usage(self):
        message = _message()
        update, context = self._run(message)

        await unverify_callback(update, context)

        self.assertEqual(self._reply(message), UNVERIFY.usage)
        context.bot.send_poll.assert_not_called()

    async def test_private_chat_is_refused(self):
        message = _message(reply_from=WILL)
        update, context = self._run(message, chat_type=ChatType.PRIVATE)

        await unverify_callback(update, context)

        self.assertIn("only works in a group chat", self._reply(message))
        context.bot.send_poll.assert_not_called()

    async def test_bots_cannot_be_unverified(self):
        message = _message(reply_from=User(id=1, first_name="ONGAbot", is_bot=True))
        update, context = self._run(message)

        await unverify_callback(update, context)

        self.assertIn("Bots are born verified", self._reply(message))
        context.bot.send_poll.assert_not_called()

    async def test_already_unverified_is_refused(self):
        message = _message(reply_from=WILL)
        update, context = self._run(message)
        self.chat.set_unverified(42, "Will", True)

        await unverify_callback(update, context)

        self.assertIn("already unverified", self._reply(message))
        context.bot.send_poll.assert_not_called()

    async def test_verifying_a_verified_member_is_refused(self):
        message = _message(reply_from=WILL)
        update, context = self._run(message)

        await verify_callback(update, context)

        self.assertIn("already verified", self._reply(message))
        context.bot.send_poll.assert_not_called()

    async def test_a_second_vote_on_the_same_member_is_refused(self):
        message = _message(reply_from=WILL)
        update, context = self._run(message)
        self.chat.add_verification_vote(VerificationVote("old", 1, 99, 42, "Will", True, MagicMock()))

        await unverify_callback(update, context)

        self.assertIn("already a vote on Will", self._reply(message))
        context.bot.send_poll.assert_not_called()

    async def test_verify_on_an_unverified_member_starts_a_vote(self):
        message = _message(reply_from=WILL)
        update, context = self._run(message)
        self.chat.set_unverified(42, "Will", True)

        await verify_callback(update, context)

        self.assertFalse(self.chat.open_vote_for(42).unverify)


if __name__ == "__main__":
    unittest.main()
