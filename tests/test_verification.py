import pickle
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from telegram import User
from telegram.error import TelegramError

from ongabot.botdata import BotData
from ongabot.chat import Chat
from ongabot.utils.points import render_leaderboard_message
from ongabot.utils.statistics import render_statistics_message
from ongabot.verification import (
    VerificationVote,
    close_vote_callback,
    reschedule_open_votes,
    schedule_close,
    start_vote,
    unverified_footer,
    verdict_text,
    vote_passes,
)
from tests import message_fixtures

NOW = datetime(2026, 9, 30, 20, 0, tzinfo=timezone.utc)


def _vote(poll_id="vote1", unverify=True, closes_at=NOW, target_id=42) -> VerificationVote:
    return VerificationVote(
        poll_id=poll_id,
        chat_id=1,
        message_id=100,
        target_id=target_id,
        target_name="Will",
        unverify=unverify,
        closes_at=closes_at,
    )


def _event_answered_by(*users: User) -> MagicMock:
    event = MagicMock()
    event.poll_answers = {user: MagicMock() for user in users}
    return event


class VotePassesTest(unittest.TestCase):
    def test_needs_three_yes_and_a_majority(self):
        cases = {(2, 0): False, (3, 0): True, (3, 2): True, (3, 3): False, (4, 5): False}
        for (yes, no), passes in cases.items():
            with self.subTest(yes=yes, no=no):
                self.assertEqual(vote_passes(yes, no), passes)


class VerdictTextTest(unittest.TestCase):
    def test_passed_unverify(self):
        text = verdict_text(_vote(), 3, 1)
        self.assertIn("3–1", text)
        self.assertIn("Will is officially unverified", text)

    def test_failed_unverify(self):
        text = verdict_text(_vote(), 2, 0)
        self.assertIn("Will keeps their ID", text)
        self.assertIn("3 yes and a majority needed", text)

    def test_passed_verify(self):
        self.assertIn("Will is verified again", verdict_text(_vote(unverify=False), 4, 0))

    def test_failed_verify(self):
        self.assertIn("Will stays 🔞", verdict_text(_vote(unverify=False), 1, 4))


class UnverifiedFooterTest(unittest.TestCase):
    def test_none_when_nobody_is_unverified(self):
        self.assertIsNone(unverified_footer([]))

    def test_lists_names_sorted_and_escaped(self):
        self.assertEqual(unverified_footer(["zed", "J.R.", "Anna"]), "🔞 Unverified: Anna, J\\.R\\., zed")

    def test_leaderboard_and_statistics_end_with_the_footer(self):
        chat = message_fixtures.chat()
        chat.set_unverified(1, "Tommy", True)

        self.assertTrue(render_leaderboard_message(chat).endswith("\n\n🔞 Unverified: Tommy"))
        self.assertTrue(render_statistics_message(chat)[0].endswith("\n\n🔞 Unverified: Tommy"))

    def test_no_footer_when_nobody_is_unverified(self):
        chat = message_fixtures.chat()

        self.assertNotIn("🔞", render_leaderboard_message(chat))
        self.assertNotIn("🔞", render_statistics_message(chat)[0])


class ChatVerificationStateTest(unittest.TestCase):
    def setUp(self):
        self.chat = Chat(chat_id=1)

    def test_new_chat_has_nobody_unverified_and_no_votes(self):
        self.assertEqual(self.chat.unverified, {})
        self.assertEqual(self.chat.verification_votes, {})

    def test_set_unverified_and_back(self):
        self.chat.set_unverified(42, "Will", True)
        self.assertTrue(self.chat.is_unverified(42))
        self.assertEqual(self.chat.unverified, {42: "Will"})

        self.chat.set_unverified(42, "Will", False)
        self.assertFalse(self.chat.is_unverified(42))

    def test_verifying_someone_never_unverified_is_a_no_op(self):
        self.chat.set_unverified(42, "Will", False)
        self.assertEqual(self.chat.unverified, {})

    def test_open_vote_for_finds_the_vote_on_that_member(self):
        vote = _vote()
        self.chat.add_verification_vote(vote)

        self.assertIs(self.chat.open_vote_for(42), vote)
        self.assertIsNone(self.chat.open_vote_for(7))

    def test_pop_removes_the_vote(self):
        self.chat.add_verification_vote(_vote())

        self.assertEqual(self.chat.pop_verification_vote("vote1").target_id, 42)
        self.assertIsNone(self.chat.pop_verification_vote("vote1"))
        self.assertIsNone(self.chat.open_vote_for(42))

    def test_defaults_state_missing_from_an_old_pickle(self):
        chat = Chat.__new__(Chat)
        chat.__setstate__({"chat_id": 1, "events": {}, "event_job": None, "pinned_polls": {}})

        self.assertEqual(chat.unverified, {})
        self.assertEqual(chat.verification_votes, {})

    def test_state_survives_a_pickle_round_trip(self):
        self.chat.set_unverified(42, "Will", True)
        self.chat.add_verification_vote(_vote(poll_id="vote2", unverify=False))

        restored = pickle.loads(pickle.dumps(self.chat))

        self.assertEqual(restored.unverified, {42: "Will"})
        self.assertEqual(restored.verification_votes["vote2"].closes_at, NOW)


class ChatFindUserByUsernameTest(unittest.TestCase):
    def setUp(self):
        self.chat = Chat(chat_id=1)

    def test_matches_case_insensitively_with_or_without_the_at(self):
        will = User(id=42, first_name="Will", is_bot=False, username="William")
        self.chat.events[date(2026, 9, 2)] = _event_answered_by(will)

        self.assertEqual(self.chat.find_user_by_username("@william"), will)
        self.assertEqual(self.chat.find_user_by_username("WILLIAM"), will)

    def test_newest_event_wins(self):
        old = User(id=42, first_name="Bill", is_bot=False, username="william")
        new = User(id=42, first_name="Will", is_bot=False, username="william")
        self.chat.events[date(2026, 9, 2)] = _event_answered_by(old)
        self.chat.events[date(2026, 9, 9)] = _event_answered_by(new)

        self.assertEqual(self.chat.find_user_by_username("william").first_name, "Will")

    def test_unknown_or_missing_username_is_none(self):
        self.chat.events[date(2026, 9, 2)] = _event_answered_by(User(id=7, first_name="Anon", is_bot=False))

        self.assertIsNone(self.chat.find_user_by_username("@nobody"))


class BotDataVerificationPollTest(unittest.TestCase):
    def setUp(self):
        self.bot_data = BotData()
        self.bot_data.get_chat(1).add_verification_vote(_vote())

    def test_is_verification_poll(self):
        self.assertTrue(self.bot_data.is_verification_poll("vote1"))
        self.assertFalse(self.bot_data.is_verification_poll("event1"))

    def test_get_event_for_a_verification_poll_logs_no_error(self):
        with self.assertNoLogs(level="ERROR"):
            self.assertIsNone(self.bot_data.get_event("vote1"))

    def test_get_event_for_an_unknown_poll_still_logs_an_error(self):
        with self.assertLogs(level="ERROR"):
            self.assertIsNone(self.bot_data.get_event("unknown"))


class ScheduleCloseTest(unittest.TestCase):
    def test_schedules_the_close_at_closes_at(self):
        job_queue = MagicMock()

        schedule_close(job_queue, _vote(closes_at=NOW + timedelta(minutes=30)), now=NOW)

        job_queue.run_once.assert_called_once_with(
            close_vote_callback,
            when=timedelta(minutes=30),
            chat_id=1,
            name="verification_vote:vote1",
            data="vote1",
        )

    def test_an_overdue_vote_closes_right_away(self):
        job_queue = MagicMock()

        schedule_close(job_queue, _vote(closes_at=NOW - timedelta(hours=2)), now=NOW)

        self.assertEqual(job_queue.run_once.call_args.kwargs["when"], timedelta(0))

    def test_reschedule_covers_every_open_vote_in_every_chat(self):
        job_queue = MagicMock()
        chat1, chat2 = Chat(1), Chat(2)
        chat1.add_verification_vote(_vote("a"))
        chat1.add_verification_vote(_vote("b", target_id=7))
        chat2.add_verification_vote(_vote("c"))

        reschedule_open_votes([chat1, chat2, Chat(3)], job_queue)

        names = [c.kwargs["name"] for c in job_queue.run_once.call_args_list]
        self.assertCountEqual(names, ["verification_vote:a", "verification_vote:b", "verification_vote:c"])


class StartVoteTest(unittest.IsolatedAsyncioTestCase):
    async def test_posts_the_poll_stores_the_vote_and_schedules_the_close(self):
        bot = MagicMock()
        message = MagicMock(message_id=100)
        message.poll.id = "vote1"
        bot.send_poll = AsyncMock(return_value=message)
        job_queue = MagicMock()
        chat = Chat(1)

        vote = await start_vote(bot, job_queue, chat, 42, "Will", unverify=True)

        bot.send_poll.assert_awaited_once_with(1, "Unverify Will? 🔞", ["Yes", "No"], is_anonymous=False)
        self.assertIs(chat.open_vote_for(42), vote)
        self.assertEqual((vote.poll_id, vote.message_id, vote.unverify), ("vote1", 100, True))
        job_queue.run_once.assert_called_once()

    async def test_verify_asks_the_reverse_question(self):
        bot = MagicMock()
        bot.send_poll = AsyncMock(return_value=MagicMock(message_id=100))

        await start_vote(bot, MagicMock(), Chat(1), 42, "Will", unverify=False)

        self.assertEqual(bot.send_poll.call_args.args[1], "Verify Will again? ✅")


class CloseVoteCallbackTest(unittest.IsolatedAsyncioTestCase):
    def _context(self, vote, yes, no):
        bot_data = BotData()
        self.chat = bot_data.get_chat(1)
        if vote is not None:
            self.chat.add_verification_vote(vote)
        context = MagicMock()
        context.bot_data = bot_data
        context.job.data = "vote1"
        context.job.chat_id = 1
        poll = MagicMock()
        poll.options = [MagicMock(voter_count=yes), MagicMock(voter_count=no)]
        context.bot.stop_poll = AsyncMock(return_value=poll)
        context.bot.send_message = AsyncMock()
        return context

    async def test_passed_unverify_marks_the_member_and_posts_the_verdict(self):
        context = self._context(_vote(), yes=3, no=1)

        await close_vote_callback(context)

        context.bot.stop_poll.assert_awaited_once_with(1, 100)
        self.assertTrue(self.chat.is_unverified(42))
        self.assertEqual(self.chat.verification_votes, {})
        args, kwargs = context.bot.send_message.call_args
        self.assertEqual(args[0], 1)
        self.assertIn("officially unverified", args[1])
        self.assertEqual(kwargs["reply_parameters"].message_id, 100)

    async def test_failed_unverify_changes_nothing(self):
        context = self._context(_vote(), yes=2, no=0)

        await close_vote_callback(context)

        self.assertFalse(self.chat.is_unverified(42))
        self.assertIn("keeps their ID", context.bot.send_message.call_args.args[1])

    async def test_passed_verify_removes_the_badge(self):
        context = self._context(_vote(unverify=False), yes=3, no=0)
        self.chat.set_unverified(42, "Will", True)

        await close_vote_callback(context)

        self.assertFalse(self.chat.is_unverified(42))

    async def test_a_poll_that_cannot_be_stopped_drops_the_vote(self):
        context = self._context(_vote(), yes=3, no=0)
        context.bot.stop_poll.side_effect = TelegramError("message to stop not found")

        await close_vote_callback(context)

        self.assertEqual(self.chat.verification_votes, {})
        self.assertFalse(self.chat.is_unverified(42))
        context.bot.send_message.assert_not_called()

    async def test_an_unknown_vote_does_nothing(self):
        context = self._context(None, yes=3, no=0)

        await close_vote_callback(context)

        context.bot.stop_poll.assert_not_called()
        context.bot.send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
