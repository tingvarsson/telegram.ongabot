import re
import unittest

from telegram.ext import CommandHandler

from ongabot.ongabot import register_handlers
from ongabot.utils.commands import (
    ALL_COMMANDS,
    BOT_DESCRIPTION,
    BOT_SHORT_DESCRIPTION,
    NEWEVENT,
    PRIVATE_COMMAND_NAMES,
    PRIVATE_COMMANDS,
)

# Registered but deliberately left out of /help and the command menu: Telegram sends /start by
# itself when someone first opens the bot, and it just replies with the help text.
HIDDEN_COMMANDS = {"start"}

# Telegram's rule for a BotCommand name.
_COMMAND_NAME_RE = re.compile(r"^[a-z0-9_]{1,32}$")


class _RecordingApplication:
    """Stands in for telegram.ext.Application, keeping every handler register_handlers adds."""

    def __init__(self):
        self.handlers = []

    def add_handler(self, handler, group=0):
        self.handlers.append((handler, group))


def _registered_commands():
    app = _RecordingApplication()
    register_handlers(app)
    commands = []
    for handler, _ in app.handlers:
        if isinstance(handler, CommandHandler):
            commands.extend(handler.commands)
    return commands


class NeweventMenuDescriptionTest(unittest.TestCase):
    def test_menu_description_includes_force_arg(self):
        self.assertIn("force", NEWEVENT.menu_description)


class CommandInfoMenuDescriptionTest(unittest.TestCase):
    def test_all_commands_have_menu_description(self):
        for cmd in ALL_COMMANDS:
            self.assertTrue(cmd.menu_description, f"{cmd.command} missing menu_description")

    def test_bot_short_description_within_telegram_limit(self):
        self.assertLessEqual(len(BOT_SHORT_DESCRIPTION), 120)

    def test_bot_description_within_telegram_limit(self):
        self.assertLessEqual(len(BOT_DESCRIPTION), 512)

    def test_all_commands_menu_description_within_telegram_limit(self):
        for cmd in ALL_COMMANDS:
            self.assertLessEqual(len(cmd.menu_description), 256, f"{cmd.command} menu_description too long")


class CommandRegistrationTest(unittest.TestCase):
    """Every command the bot answers is documented, and every documented command is answered."""

    def test_documented_commands_match_registered_handlers(self):
        documented = {cmd.command for cmd in ALL_COMMANDS}
        registered = set(_registered_commands()) - HIDDEN_COMMANDS
        self.assertEqual(
            registered - documented, set(), "handled but missing from ALL_COMMANDS, so absent from /help and the menu"
        )
        self.assertEqual(documented - registered, set(), "listed in /help and the menu but no handler answers it")

    def test_no_command_is_registered_twice(self):
        commands = _registered_commands()
        self.assertEqual(len(commands), len(set(commands)))

    def test_no_command_is_documented_twice(self):
        names = [cmd.command for cmd in ALL_COMMANDS]
        self.assertEqual(len(names), len(set(names)))


class PrivateCommandsTest(unittest.TestCase):
    """The commands a private chat with the bot answers - the gate, private /help and menu use these."""

    def test_exactly_the_read_and_per_user_commands_are_private(self):
        self.assertEqual(
            [cmd.command for cmd in PRIVATE_COMMANDS],
            ["help", "statistics", "leaderboard", "cs2", "topics", "linksteam", "unlinksteam"],
        )

    def test_start_passes_the_gate_although_hidden_from_help(self):
        self.assertIn("start", PRIVATE_COMMAND_NAMES)

    def test_every_private_command_is_registered(self):
        self.assertLessEqual(PRIVATE_COMMAND_NAMES, set(_registered_commands()))


class CommandInfoConsistencyTest(unittest.TestCase):
    """The brief, usage and menu text of a command all describe that same command."""

    def test_command_names_are_valid_for_telegram(self):
        for cmd in ALL_COMMANDS:
            self.assertRegex(cmd.command, _COMMAND_NAME_RE)

    def test_brief_starts_with_its_own_command(self):
        for cmd in ALL_COMMANDS:
            self.assertRegex(cmd.brief, rf"^/{cmd.command}( |$)", f"{cmd.command} brief names another command")

    def test_usage_shows_its_own_command(self):
        for cmd in ALL_COMMANDS:
            self.assertRegex(cmd.usage, rf"/{cmd.command}\b", f"{cmd.command} usage never shows /{cmd.command}")

    def test_menu_description_is_a_phrase_not_a_command(self):
        # The menu already shows the command name next to the description.
        for cmd in ALL_COMMANDS:
            self.assertFalse(cmd.menu_description.startswith("/"), cmd.command)


if __name__ == "__main__":
    unittest.main()
