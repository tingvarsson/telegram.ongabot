import unittest

from ongabot.botdata import BotData


class BotDataDefaultsTest(unittest.TestCase):
    def test_last_known_version_defaults_to_none(self):
        bd = BotData()
        self.assertIsNone(bd.last_known_version)

    def test_last_known_version_can_be_set(self):
        bd = BotData()
        bd.last_known_version = "1.2.0"
        self.assertEqual(bd.last_known_version, "1.2.0")


class BotDataSetStateTest(unittest.TestCase):
    def test_migration_adds_last_known_version_when_missing(self):
        bd = BotData.__new__(BotData)
        # Simulate an old pickle that has no last_known_version
        bd.__setstate__({"chats": {}, "authorized_chats": set()})
        self.assertIsNone(bd.last_known_version)

    def test_migration_preserves_existing_last_known_version(self):
        bd = BotData.__new__(BotData)
        bd.__setstate__({"chats": {}, "authorized_chats": set(), "last_known_version": "1.1.0"})
        self.assertEqual(bd.last_known_version, "1.1.0")

    def test_migration_adds_authorized_chats_when_missing(self):
        bd = BotData.__new__(BotData)
        bd.__setstate__({"chats": {}})
        self.assertEqual(bd.authorized_chats, set())


if __name__ == "__main__":
    unittest.main()
