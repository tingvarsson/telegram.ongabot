"""Scheduling for the daily YouTube Short: a random time within a window, per chat, per day.

Mirrors the CS2 sweep's scheduling pattern (see test_cs2sweep.py): JobQueue state is not
persisted, so an hourly, idempotent re-derivation job is what resumes a lost post-time choice
after a restart.
"""

import os
import unittest
from datetime import date, datetime, time
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.error import TelegramError

from ongabot import ongabot
from ongabot.youtube.selection import SelectedVideo

CHAT_ID = 123


def _video(video_id="abc", topics=("linux",)):
    return SelectedVideo(
        video_id=video_id, title="A Short", url=f"https://www.youtube.com/shorts/{video_id}", topics=topics
    )


class ShortsWindowConfigTest(unittest.TestCase):
    def setUp(self):
        self._old_start = os.environ.pop("YOUTUBE_SHORTS_WINDOW_START", None)
        self._old_end = os.environ.pop("YOUTUBE_SHORTS_WINDOW_END", None)

    def tearDown(self):
        for var, old in (
            ("YOUTUBE_SHORTS_WINDOW_START", self._old_start),
            ("YOUTUBE_SHORTS_WINDOW_END", self._old_end),
        ):
            os.environ.pop(var, None)
            if old is not None:
                os.environ[var] = old

    def test_defaults_to_ten_to_twenty(self):
        self.assertEqual(ongabot.shorts_window(), (time(10, 0), time(20, 0)))

    def test_env_vars_override_the_default(self):
        os.environ["YOUTUBE_SHORTS_WINDOW_START"] = "08:15"
        os.environ["YOUTUBE_SHORTS_WINDOW_END"] = "22:45"

        self.assertEqual(ongabot.shorts_window(), (time(8, 15), time(22, 45)))

    def test_falls_back_to_the_default_for_a_malformed_value(self):
        os.environ["YOUTUBE_SHORTS_WINDOW_START"] = "not-a-time"

        self.assertEqual(ongabot.shorts_window()[0], time(10, 0))


class ShortsJobNameTest(unittest.TestCase):
    def test_includes_chat_id_and_date(self):
        name = ongabot.shorts_job_name(CHAT_ID, date(2026, 9, 2))

        self.assertIn(str(CHAT_ID), name)
        self.assertIn("2026-09-02", name)


class ScheduleTodaysShortTest(unittest.TestCase):
    def setUp(self):
        self.job_queue = MagicMock()
        self.job_queue.get_jobs_by_name.return_value = []
        self.chat = MagicMock()
        self.chat.chat_id = CHAT_ID
        self.chat.last_shorts_posted_date = None
        self._old_start = os.environ.pop("YOUTUBE_SHORTS_WINDOW_START", None)
        self._old_end = os.environ.pop("YOUTUBE_SHORTS_WINDOW_END", None)

    def tearDown(self):
        for var, old in (
            ("YOUTUBE_SHORTS_WINDOW_START", self._old_start),
            ("YOUTUBE_SHORTS_WINDOW_END", self._old_end),
        ):
            os.environ.pop(var, None)
            if old is not None:
                os.environ[var] = old

    def test_schedules_a_run_once_job_within_the_window(self):
        today = date(2026, 9, 2)
        now = datetime.combine(today, time(9, 0))

        ongabot.schedule_todays_short(self.job_queue, self.chat, today, now)

        self.job_queue.run_once.assert_called_once()
        kwargs = self.job_queue.run_once.call_args.kwargs
        self.assertEqual(kwargs["chat_id"], CHAT_ID)
        self.assertIn(str(today), kwargs["name"])
        self.assertGreaterEqual(kwargs["when"], datetime.combine(today, time(10, 0)))
        self.assertLessEqual(kwargs["when"], datetime.combine(today, time(20, 0)))

    def test_uses_now_as_the_earliest_possible_time_when_already_inside_the_window(self):
        today = date(2026, 9, 2)
        now = datetime.combine(today, time(15, 0))

        ongabot.schedule_todays_short(self.job_queue, self.chat, today, now)

        when = self.job_queue.run_once.call_args.kwargs["when"]
        self.assertGreaterEqual(when, now)
        self.assertLessEqual(when, datetime.combine(today, time(20, 0)))

    def test_skips_when_already_posted_today(self):
        today = date(2026, 9, 2)
        self.chat.last_shorts_posted_date = today

        ongabot.schedule_todays_short(self.job_queue, self.chat, today, datetime.combine(today, time(9, 0)))

        self.job_queue.run_once.assert_not_called()

    def test_skips_when_already_scheduled(self):
        self.job_queue.get_jobs_by_name.return_value = [MagicMock()]
        today = date(2026, 9, 2)

        ongabot.schedule_todays_short(self.job_queue, self.chat, today, datetime.combine(today, time(9, 0)))

        self.job_queue.run_once.assert_not_called()

    def test_skips_when_the_window_has_already_closed_for_today(self):
        today = date(2026, 9, 2)
        now = datetime.combine(today, time(21, 0))

        ongabot.schedule_todays_short(self.job_queue, self.chat, today, now)

        self.job_queue.run_once.assert_not_called()


class ScheduleTodaysShortsCallbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_schedules_a_short_for_every_authorized_chat(self):
        chat = MagicMock()
        context = MagicMock()
        context.bot_data.authorized_chats = {CHAT_ID}
        context.bot_data.get_chat.return_value = chat

        with patch("ongabot.ongabot.schedule_todays_short") as schedule:
            await ongabot.schedule_todays_shorts_callback(context)

        schedule.assert_called_once()
        self.assertIs(schedule.call_args.args[0], context.job_queue)
        self.assertIs(schedule.call_args.args[1], chat)

    async def test_no_authorized_chats_schedules_nothing(self):
        context = MagicMock()
        context.bot_data.authorized_chats = set()

        with patch("ongabot.ongabot.schedule_todays_short") as schedule:
            await ongabot.schedule_todays_shorts_callback(context)

        schedule.assert_not_called()


def _post_context(chat=None):
    if chat is None:
        chat = MagicMock()
        chat.chat_id = CHAT_ID
        chat.topic_scores = {"linux": 3.0}
        chat.last_shorts_posted_date = None

    context = MagicMock()
    context.job.chat_id = CHAT_ID
    context.bot_data.get_chat.return_value = chat
    context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=999))
    return context, chat


class PostShortsCallbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_posts_the_selected_video_and_records_it(self):
        context, chat = _post_context()
        video = _video()

        with patch("ongabot.ongabot.choose_topic", return_value="linux"):
            with patch("ongabot.ongabot.pick_short", AsyncMock(return_value=video)):
                with patch("ongabot.ongabot.register_topics") as register:
                    await ongabot.post_shorts_callback(context)

        context.bot.send_message.assert_awaited_once_with(CHAT_ID, video.url)
        chat.record_shorts_post.assert_called_once()
        self.assertEqual(chat.record_shorts_post.call_args.args[0], 999)
        self.assertIs(chat.record_shorts_post.call_args.args[1], video)
        register.assert_called_once_with(chat.topic_scores, video.topics)

    async def test_skips_when_already_posted_today(self):
        context, chat = _post_context()
        chat.last_shorts_posted_date = date.today()

        with patch("ongabot.ongabot.pick_short", AsyncMock()) as pick:
            await ongabot.post_shorts_callback(context)

        pick.assert_not_awaited()
        context.bot.send_message.assert_not_awaited()

    async def test_retries_with_a_second_topic_when_the_first_yields_nothing(self):
        context, chat = _post_context()
        video = _video()

        with patch("ongabot.ongabot.choose_topic", side_effect=["linux", "counter-strike"]):
            with patch("ongabot.ongabot.pick_short", AsyncMock(side_effect=[None, video])) as pick:
                await ongabot.post_shorts_callback(context)

        self.assertEqual(pick.await_count, 2)
        context.bot.send_message.assert_awaited_once_with(CHAT_ID, video.url)

    async def test_no_eligible_video_leaves_chat_unposted_for_a_later_retry(self):
        context, chat = _post_context()

        with patch("ongabot.ongabot.choose_topic", side_effect=["linux", "linux"]):
            with patch("ongabot.ongabot.pick_short", AsyncMock(return_value=None)):
                await ongabot.post_shorts_callback(context)

        context.bot.send_message.assert_not_awaited()
        chat.record_shorts_post.assert_not_called()

    async def test_failed_send_does_not_record_the_post(self):
        context, chat = _post_context()
        context.bot.send_message = AsyncMock(side_effect=TelegramError("boom"))
        video = _video()

        with patch("ongabot.ongabot.choose_topic", return_value="linux"):
            with patch("ongabot.ongabot.pick_short", AsyncMock(return_value=video)):
                await ongabot.post_shorts_callback(context)

        chat.record_shorts_post.assert_not_called()


class DecayShortsTopicScoresCallbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_decays_every_chats_topic_scores(self):
        chat1 = MagicMock(topic_scores={"linux": 5.0})
        chat2 = MagicMock(topic_scores={"counter-strike": 2.0})
        context = MagicMock()
        context.bot_data.chats = {1: chat1, 2: chat2}

        with patch("ongabot.ongabot.decay_topic_scores") as decay:
            await ongabot.decay_shorts_topic_scores_callback(context)

        self.assertEqual(decay.call_count, 2)
        decay.assert_any_call(chat1.topic_scores)
        decay.assert_any_call(chat2.topic_scores)


if __name__ == "__main__":
    unittest.main()
