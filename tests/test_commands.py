import unittest

from ongabot.utils.commands import ALL_COMMANDS, BOT_DESCRIPTION, BOT_SHORT_DESCRIPTION, NEWEVENT


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


if __name__ == "__main__":
    unittest.main()
