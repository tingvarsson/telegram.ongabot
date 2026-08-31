import unittest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.constants import ParseMode

from ongabot.handler.cs2commandhandler import callback


def _event(event_date, completed=True, cancelled=False):
    event = MagicMock()
    event.event_date = event_date
    event.completed = completed
    event.cancelled = cancelled
    return event


def _make(args=None, events=None):
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_chat.id = 123

    chat = MagicMock()
    chat.events = {event.event_date: event for event in (events or [_event(date(2026, 9, 2))])}
    # Mirror the real Chat.get_event_by_date, so "no event on that date" is reachable.
    chat.get_event_by_date.side_effect = chat.events.get

    context = MagicMock()
    context.args = args or []
    context.bot_data.get_chat.return_value = chat
    context.application.user_data = {}

    return update, context, chat


def _reply(update):
    return update.message.reply_text.await_args.args[0]


class Cs2CommandHandlerTest(unittest.IsolatedAsyncioTestCase):
    async def test_reports_the_latest_event_by_default(self):
        update, context, chat = _make()

        with patch(
            "ongabot.handler.cs2commandhandler.event_results",
            AsyncMock(return_value=(MagicMock(), "RESULTS")),
        ) as results:
            await callback(update, context)

        self.assertIs(results.await_args.args[1], chat)
        self.assertEqual(results.await_args.args[2].event_date, date(2026, 9, 2))
        update.message.reply_text.assert_awaited_once()
        self.assertEqual(update.message.reply_text.await_args.args, ("RESULTS",))
        kwargs = update.message.reply_text.await_args.kwargs
        self.assertEqual(kwargs["parse_mode"], ParseMode.MARKDOWN_V2)
        self.assertTrue(kwargs["link_preview_options"].is_disabled, "Leetify links must not preview")

    async def test_reports_the_event_named_by_target_date(self):
        events = [_event(date(2026, 8, 26)), _event(date(2026, 9, 2))]
        update, context, _chat = _make(args=["target_date=2026-08-26"], events=events)

        with patch(
            "ongabot.handler.cs2commandhandler.event_results",
            AsyncMock(return_value=(MagicMock(), "RESULTS")),
        ) as results:
            await callback(update, context)

        self.assertEqual(results.await_args.args[2].event_date, date(2026, 8, 26))

    async def test_says_so_when_there_is_no_event_for_the_target_date(self):
        update, context, _chat = _make(args=["target_date=2026-01-01"])

        with patch("ongabot.handler.cs2commandhandler.event_results", AsyncMock()) as results:
            await callback(update, context)

        results.assert_not_awaited()
        self.assertIn("2026-01-01", _reply(update))

    async def test_shows_usage_for_an_unparseable_target_date(self):
        update, context, _chat = _make(args=["target_date=nonsense"])

        with patch("ongabot.handler.cs2commandhandler.event_results", AsyncMock()) as results:
            await callback(update, context)

        results.assert_not_awaited()
        self.assertIn("/cs2", _reply(update))

    async def test_says_so_when_the_chat_has_no_completed_events(self):
        update, context, _chat = _make(events=[_event(date(2026, 9, 9), completed=False)])

        with patch("ongabot.handler.cs2commandhandler.event_results", AsyncMock()) as results:
            await callback(update, context)

        results.assert_not_awaited()
        update.message.reply_text.assert_awaited_once()

    async def test_reports_the_outage_instead_of_claiming_nobody_played(self):
        update, context, _chat = _make()

        with patch(
            "ongabot.handler.cs2commandhandler.event_results",
            AsyncMock(return_value=(None, None)),
        ):
            await callback(update, context)

        self.assertIn("Leetify", _reply(update))


if __name__ == "__main__":
    unittest.main()
