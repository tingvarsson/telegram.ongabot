"""Which moments get a GIF: swing moods and their dice-and-cooldown gate, the stack, CS2 nights."""

import unittest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

# Imported the way the bot imports them, with ongabot/ on the path: moments compares Answer and
# Mood members by identity, and ongabot.quips.Answer would be a different class from the
# quips.Answer that moments sees.
from chat import Chat
from cs2.session import Cs2Match, Cs2Session
from gifs import moments
from gifs.moods import Mood
from quips import Answer

CHAT_ID = 42


def _match(score):
    return Cs2Match(id=str(score), map_name="de_dust2", finished_at=None, score=score, our_team=2, players=())


def _session(*scores):
    return Cs2Session(event_date=date(2026, 10, 14), matches=[_match(score) for score in scores])


class SwingMoodTest(unittest.TestCase):
    def test_dramatic_paths_have_a_mood(self):
        self.assertIs(moments.swing_mood(Answer.GAME, Answer.NO_OP), Mood.BAIL)
        self.assertIs(moments.swing_mood(Answer.NO_OP, Answer.GAME), Mood.COMEBACK)
        self.assertIs(moments.swing_mood(Answer.GAME, None), Mood.GHOSTED)

    def test_every_other_path_has_none(self):
        dramatic = {(Answer.GAME, Answer.NO_OP), (Answer.NO_OP, Answer.GAME), (Answer.GAME, None)}
        for previous in (None, *Answer):
            for new in (None, *Answer):
                if (previous, new) in dramatic:
                    continue
                with self.subTest(previous=previous, new=new):
                    self.assertIsNone(moments.swing_mood(previous, new))


class SwingGateTest(unittest.TestCase):
    def setUp(self):
        moments.reset()
        self.addCleanup(moments.reset)
        self.now = 1000.0
        clock = patch.object(moments, "_clock", side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.roll = 0.0
        self.dice = patch.object(moments.random, "random", side_effect=lambda: self.roll).start()
        self.addCleanup(patch.stopall)
        self.chat = Chat(CHAT_ID)

    def test_a_winning_roll_gets_a_gif(self):
        with self.assertLogs("gifs.moments", level="INFO"):
            self.assertIs(moments.gated_swing_mood(self.chat, Answer.GAME, Answer.NO_OP), Mood.BAIL)

    def test_a_losing_roll_does_not(self):
        self.roll = moments.SWING_GIF_CHANCE
        with self.assertLogs("gifs.moments", level="INFO") as logs:
            self.assertIsNone(moments.gated_swing_mood(self.chat, Answer.GAME, Answer.NO_OP))
        self.assertIn("roll", "\n".join(logs.output))

    def test_the_cooldown_holds_back_the_next_one(self):
        moments.gated_swing_mood(self.chat, Answer.GAME, Answer.NO_OP)
        self.now += moments.SWING_GIF_COOLDOWN_SECONDS - 1

        with self.assertLogs("gifs.moments", level="INFO") as logs:
            self.assertIsNone(moments.gated_swing_mood(self.chat, Answer.NO_OP, Answer.GAME))
        self.assertIn("cooldown", "\n".join(logs.output))

        self.now += 1
        self.assertIs(moments.gated_swing_mood(self.chat, Answer.NO_OP, Answer.GAME), Mood.COMEBACK)

    def test_the_cooldown_is_per_chat(self):
        moments.gated_swing_mood(self.chat, Answer.GAME, Answer.NO_OP)
        self.assertIs(moments.gated_swing_mood(Chat(CHAT_ID + 1), Answer.GAME, Answer.NO_OP), Mood.BAIL)

    def test_a_lost_roll_does_not_start_the_cooldown(self):
        self.roll = 0.99
        moments.gated_swing_mood(self.chat, Answer.GAME, Answer.NO_OP)
        self.roll = 0.0
        self.assertIs(moments.gated_swing_mood(self.chat, Answer.GAME, Answer.NO_OP), Mood.BAIL)

    def test_a_chat_with_gifs_off_neither_rolls_nor_starts_the_cooldown(self):
        self.chat.gifs_enabled = False
        with self.assertNoLogs("gifs.moments", level="INFO"):
            self.assertIsNone(moments.gated_swing_mood(self.chat, Answer.GAME, Answer.NO_OP))
        self.dice.assert_not_called()

        self.chat.gifs_enabled = True
        self.assertIs(moments.gated_swing_mood(self.chat, Answer.GAME, Answer.NO_OP), Mood.BAIL)

    def test_a_quiet_path_neither_rolls_nor_starts_the_cooldown(self):
        self.assertIsNone(moments.gated_swing_mood(self.chat, None, Answer.GAME))
        self.assertIs(moments.gated_swing_mood(self.chat, Answer.GAME, Answer.NO_OP), Mood.BAIL)


class StackTextTest(unittest.TestCase):
    def test_names_the_slot(self):
        self.assertEqual(moments.stack_full_text("19.10"), "🎉 Five-stack at 19.10!")


class Cs2VerdictTest(unittest.TestCase):
    def test_a_winning_night(self):
        self.assertEqual(
            moments.cs2_verdict(_session((13, 7), (13, 11), (5, 13))), (Mood.CS2_WIN, "Night's over: 2W 1L")
        )

    def test_a_losing_night(self):
        self.assertEqual(moments.cs2_verdict(_session((7, 13))), (Mood.CS2_LOSS, "Night's over: 0W 1L"))

    def test_draws_are_shown_but_do_not_decide(self):
        self.assertEqual(moments.cs2_verdict(_session((13, 7), (12, 12))), (Mood.CS2_WIN, "Night's over: 1W 0L 1D"))

    def test_an_even_night_gets_nothing(self):
        self.assertIsNone(moments.cs2_verdict(_session((13, 7), (7, 13))))
        self.assertIsNone(moments.cs2_verdict(_session((12, 12))))
        self.assertIsNone(moments.cs2_verdict(_session()))


class SendCs2VerdictTest(unittest.IsolatedAsyncioTestCase):
    async def test_replies_to_the_results_with_a_gif_only(self):
        chat = Chat(CHAT_ID)
        bot = MagicMock()
        with patch.object(moments, "send_with_gif", AsyncMock()) as send:
            await moments.send_cs2_verdict(bot, chat, _session((13, 7)), 99, disable_notification=True)

        send.assert_awaited_once()
        args, kwargs = send.call_args
        self.assertEqual(args, (bot, chat, "Night's over: 1W 0L", Mood.CS2_WIN))
        self.assertFalse(kwargs["text_fallback"])
        self.assertTrue(kwargs["disable_notification"])
        self.assertEqual(kwargs["reply_parameters"].message_id, 99)
        self.assertTrue(kwargs["reply_parameters"].allow_sending_without_reply)

    async def test_an_even_night_sends_nothing(self):
        with patch.object(moments, "send_with_gif", AsyncMock()) as send:
            await moments.send_cs2_verdict(MagicMock(), Chat(CHAT_ID), _session((13, 7), (7, 13)), 99)
        send.assert_not_awaited()


class SendStackCelebrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_replies_to_the_pinned_poll(self):
        chat = Chat(CHAT_ID)
        chat.pinned_polls["poll"] = MagicMock(message_id=55)
        bot = MagicMock()
        with patch.object(moments, "send_with_gif", AsyncMock()) as send:
            await moments.send_stack_celebration(bot, chat, "poll", "19.10")

        args, kwargs = send.call_args
        self.assertEqual(args, (bot, chat, "🎉 Five-stack at 19.10!", Mood.STACK_FULL))
        self.assertEqual(kwargs["reply_parameters"].message_id, 55)

    async def test_no_reply_once_the_poll_is_unpinned(self):
        with patch.object(moments, "send_with_gif", AsyncMock()) as send:
            await moments.send_stack_celebration(MagicMock(), Chat(CHAT_ID), "poll", "19.10")
        self.assertIsNone(send.call_args.kwargs["reply_parameters"])
