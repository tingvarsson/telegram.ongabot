import unittest
from unittest.mock import AsyncMock, MagicMock

from ongabot.handler.topicscommandhandler import callback


def _make(topic_scores):
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_chat.id = 123

    chat = MagicMock()
    chat.topic_scores = topic_scores

    context = MagicMock()
    context.bot_data.get_chat.return_value = chat

    return update, context


def _reply(update):
    return update.message.reply_text.await_args.args[0]


class TopicsCommandHandlerTest(unittest.IsolatedAsyncioTestCase):
    async def test_replies_with_topics_sorted_by_score_descending(self):
        update, context = _make({"linux": 2.0, "counter-strike": 4.5, "speedrun": 1.0})

        await callback(update, context)

        text = _reply(update)
        self.assertLess(text.index("counter-strike"), text.index("linux"))
        self.assertLess(text.index("linux"), text.index("speedrun"))

    async def test_scores_are_shown(self):
        update, context = _make({"linux": 3.25})

        await callback(update, context)

        self.assertIn("3.25", _reply(update))

    async def test_replies_with_a_placeholder_when_no_topics_tracked_yet(self):
        update, context = _make({})

        await callback(update, context)

        self.assertNotEqual(_reply(update), "")

    async def test_does_nothing_without_a_message(self):
        update, context = _make({"linux": 1.0})
        update.message = None

        await callback(update, context)

        context.bot_data.get_chat.assert_not_called()


if __name__ == "__main__":
    unittest.main()
