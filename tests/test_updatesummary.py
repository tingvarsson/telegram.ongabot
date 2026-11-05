import datetime
import logging
import unittest

from telegram import CallbackQuery, Chat, ChatMemberLeft, ChatMemberMember, ChatMemberUpdated, Message, PollAnswer
from telegram import Update, User
from telegram.constants import ChatType

from ongabot.handler.authorizationhandler import AuthorizationHandler
from ongabot.handler.updatelogginghandler import UpdateLoggingHandler, callback
from ongabot.ongabot import register_handlers
from ongabot.utils.updatesummary import command_of, describe_update

GROUP = Chat(id=-100123, type=ChatType.SUPERGROUP)
USER = User(id=7, first_name="Alice", is_bot=False)
BOT = User(id=99, first_name="ONGAbot", is_bot=True)
NOW = datetime.datetime(2026, 11, 5, 19, 58, tzinfo=datetime.UTC)
FROM_GROUP = "from user_id=7 in chat_id=-100123 (supergroup)"


def _message(text, chat=GROUP):
    return Message(message_id=1, date=NOW, chat=chat, from_user=USER, text=text)


def _answer(option_ids):
    return PollAnswer("p1", option_ids, user=USER, option_persistent_ids=[str(i) for i in option_ids])


class CommandOfTest(unittest.TestCase):
    def test_strips_bot_name_and_arguments_and_lowercases(self):
        update = Update(update_id=1, message=_message("/Onga@ONGAbot some args"))
        self.assertEqual(command_of(update), "/onga")

    def test_plain_text_is_not_a_command(self):
        self.assertIsNone(command_of(Update(update_id=1, message=_message("hello"))))

    def test_update_without_message_is_not_a_command(self):
        self.assertIsNone(command_of(Update(update_id=1, poll_answer=_answer((0,)))))


class DescribeUpdateTest(unittest.TestCase):
    def test_command_is_info_without_its_arguments(self):
        level, summary = describe_update(Update(update_id=1, message=_message("/linksteam https://steam/me")))
        self.assertEqual(level, logging.INFO)
        self.assertEqual(summary, f"/linksteam {FROM_GROUP}")

    def test_command_in_a_private_chat(self):
        private = Chat(id=7, type=ChatType.PRIVATE)
        _, summary = describe_update(Update(update_id=1, message=_message("/statistics", chat=private)))
        self.assertEqual(summary, "/statistics from user_id=7 in chat_id=7 (private)")

    def test_button_tap_is_info_with_its_data(self):
        query = CallbackQuery("q1", USER, "inst", data="stats_sort:played:-100123", message=_message("stats"))
        level, summary = describe_update(Update(update_id=1, callback_query=query))
        self.assertEqual(level, logging.INFO)
        self.assertEqual(summary, f"button 'stats_sort:played:-100123' {FROM_GROUP}")

    def test_poll_answer_is_info_with_the_options(self):
        level, summary = describe_update(Update(update_id=1, poll_answer=_answer((0, 2))))
        self.assertEqual(level, logging.INFO)
        self.assertEqual(summary, "poll answer (options [0, 2]) on poll_id=p1 from user_id=7")

    def test_retracted_poll_answer(self):
        _, summary = describe_update(Update(update_id=1, poll_answer=_answer(())))
        self.assertEqual(summary, "poll answer (retracted vote) on poll_id=p1 from user_id=7")

    def test_bot_added_to_a_group_is_info(self):
        change = ChatMemberUpdated(GROUP, USER, NOW, ChatMemberLeft(BOT), ChatMemberMember(BOT))
        level, summary = describe_update(Update(update_id=1, my_chat_member=change))
        self.assertEqual(level, logging.INFO)
        self.assertEqual(summary, f"bot membership is now member {FROM_GROUP}")

    def test_plain_message_is_debug_without_its_text(self):
        level, summary = describe_update(Update(update_id=1, message=_message("secret plans")))
        self.assertEqual(level, logging.DEBUG)
        self.assertEqual(summary, f"message {FROM_GROUP}")

    def test_edited_command_is_debug_and_named_by_kind(self):
        level, summary = describe_update(Update(update_id=1, edited_message=_message("/onga")))
        self.assertEqual(level, logging.DEBUG)
        self.assertEqual(summary, f"edited_message {FROM_GROUP}")


class UpdateLoggingHandlerTest(unittest.IsolatedAsyncioTestCase):
    async def test_logs_the_summary_with_the_update_id(self):
        update = Update(update_id=4711, message=_message("/onga"))
        with self.assertLogs("ongabot.handler.updatelogginghandler", logging.INFO) as logs:
            await callback(update, None)
        self.assertEqual(logs.output, [f"INFO:ongabot.handler.updatelogginghandler:Update 4711: /onga {FROM_GROUP}"])

    def test_handles_every_update(self):
        self.assertTrue(UpdateLoggingHandler().check_update(Update(update_id=1, message=_message("hi"))))


class _RecordingApplication:
    def __init__(self):
        self.handlers = []

    def add_handler(self, handler, group=0):
        self.handlers.append((handler, group))


class RegistrationTest(unittest.TestCase):
    def test_update_logging_runs_before_the_authorization_gate(self):
        app = _RecordingApplication()
        register_handlers(app)
        # By name: register_handlers imports these as handler.*, a separate module from ongabot.handler.*.
        groups = {type(handler).__name__: group for handler, group in app.handlers}
        self.assertLess(groups[UpdateLoggingHandler.__name__], groups[AuthorizationHandler.__name__])


if __name__ == "__main__":
    unittest.main()
