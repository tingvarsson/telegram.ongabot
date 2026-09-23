import unittest
from unittest.mock import MagicMock

from telegram import ReactionTypeEmoji
from telegram.constants import ReactionEmoji

from ongabot.handler.shortsreactionhandler import callback
from ongabot.youtube.selection import PostedShort

THUMBS_UP = ReactionTypeEmoji(emoji=ReactionEmoji.THUMBS_UP)
THUMBS_DOWN = ReactionTypeEmoji(emoji=ReactionEmoji.THUMBS_DOWN)


def _reaction(chat_id=123, message_id=42, old=(), new=()):
    reaction = MagicMock()
    reaction.chat.id = chat_id
    reaction.message_id = message_id
    reaction.old_reaction = old
    reaction.new_reaction = new
    return reaction


def _chat(posted_shorts=None, topic_scores=None):
    chat = MagicMock()
    chat.chat_id = 123
    chat.posted_shorts = posted_shorts or {}
    chat.topic_scores = topic_scores if topic_scores is not None else {}
    return chat


def _context(chat):
    context = MagicMock()
    context.bot_data.get_chat.return_value = chat
    return context


class ShortsReactionHandlerTest(unittest.IsolatedAsyncioTestCase):
    async def test_applies_a_positive_reaction_to_the_videos_topics(self):
        posted = PostedShort(video_id="abc", topics=("linux",), posted_at=MagicMock())
        chat = _chat(posted_shorts={42: posted}, topic_scores={"linux": 1.0})
        update = MagicMock(message_reaction=_reaction(new=(THUMBS_UP,)))

        await callback(update, _context(chat))

        self.assertEqual(chat.topic_scores["linux"], 1.5)

    async def test_no_op_for_a_message_not_in_posted_shorts(self):
        chat = _chat(posted_shorts={}, topic_scores={"linux": 1.0})
        update = MagicMock(message_reaction=_reaction(new=(THUMBS_UP,)))

        await callback(update, _context(chat))

        self.assertEqual(chat.topic_scores, {"linux": 1.0})

    async def test_no_op_when_reaction_change_nets_to_zero(self):
        posted = PostedShort(video_id="abc", topics=("linux",), posted_at=MagicMock())
        chat = _chat(posted_shorts={42: posted}, topic_scores={"linux": 1.0})
        update = MagicMock(message_reaction=_reaction(old=(THUMBS_UP,), new=(THUMBS_UP,)))

        await callback(update, _context(chat))

        self.assertEqual(chat.topic_scores["linux"], 1.0)

    async def test_removing_a_positive_reaction_undoes_its_boost(self):
        posted = PostedShort(video_id="abc", topics=("linux",), posted_at=MagicMock())
        chat = _chat(posted_shorts={42: posted}, topic_scores={"linux": 1.5})
        update = MagicMock(message_reaction=_reaction(old=(THUMBS_UP,), new=()))

        await callback(update, _context(chat))

        self.assertEqual(chat.topic_scores["linux"], 1.0)

    async def test_a_negative_reaction_lowers_multiple_topics_from_one_video(self):
        posted = PostedShort(video_id="abc", topics=("linux", "gaming"), posted_at=MagicMock())
        chat = _chat(posted_shorts={42: posted}, topic_scores={"linux": 1.0, "gaming": 1.0})
        update = MagicMock(message_reaction=_reaction(new=(THUMBS_DOWN,)))

        await callback(update, _context(chat))

        self.assertEqual(chat.topic_scores["linux"], 0.5)
        self.assertEqual(chat.topic_scores["gaming"], 0.5)

    async def test_no_op_when_update_has_no_message_reaction(self):
        chat = _chat()
        context = _context(chat)
        update = MagicMock(message_reaction=None)

        await callback(update, context)

        context.bot_data.get_chat.assert_not_called()


if __name__ == "__main__":
    unittest.main()
