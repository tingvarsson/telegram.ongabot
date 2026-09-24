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
    def test_migration_seeds_known_starting_point_when_missing(self):
        bd = BotData.__new__(BotData)
        # Simulate an old pickle predating version tracking
        bd.__setstate__({"chats": {}, "authorized_chats": set()})
        self.assertEqual(bd.last_known_version, "1.2.0")

    def test_migration_preserves_existing_last_known_version(self):
        bd = BotData.__new__(BotData)
        bd.__setstate__({"chats": {}, "authorized_chats": set(), "last_known_version": "1.1.0"})
        self.assertEqual(bd.last_known_version, "1.1.0")

    def test_migration_adds_authorized_chats_when_missing(self):
        bd = BotData.__new__(BotData)
        bd.__setstate__({"chats": {}})
        self.assertEqual(bd.authorized_chats, set())

    def test_migration_adds_cs2_patchnotes_state_when_missing(self):
        bd = BotData.__new__(BotData)
        bd.__setstate__({"chats": {}, "authorized_chats": set(), "last_known_version": "1.9.0"})
        self.assertEqual(bd.cs2_patchnotes_subscribers, set())
        # Unprimed, not empty: the first poll must record the feed, not announce all of it.
        self.assertIsNone(bd.cs2_patchnotes_seen_gids)

    def test_migration_preserves_existing_cs2_patchnotes_state(self):
        bd = BotData.__new__(BotData)
        bd.__setstate__({"chats": {}, "cs2_patchnotes_subscribers": {101}, "cs2_patchnotes_seen_gids": {"g1"}})
        self.assertEqual(bd.cs2_patchnotes_subscribers, {101})
        self.assertEqual(bd.cs2_patchnotes_seen_gids, {"g1"})


class BotDataCs2PatchnotesSubscriptionTest(unittest.TestCase):
    def test_new_bot_data_has_no_subscribers_and_is_unprimed(self):
        bd = BotData()
        self.assertEqual(bd.cs2_patchnotes_subscribers, set())
        self.assertIsNone(bd.cs2_patchnotes_seen_gids)

    def test_subscribe_then_unsubscribe(self):
        bd = BotData()
        bd.subscribe_to_cs2_patchnotes(101)
        self.assertTrue(bd.is_subscribed_to_cs2_patchnotes(101))
        bd.unsubscribe_from_cs2_patchnotes(101)
        self.assertFalse(bd.is_subscribed_to_cs2_patchnotes(101))

    def test_subscribing_twice_is_idempotent(self):
        bd = BotData()
        bd.subscribe_to_cs2_patchnotes(101)
        bd.subscribe_to_cs2_patchnotes(101)
        self.assertEqual(bd.cs2_patchnotes_subscribers, {101})

    def test_unsubscribing_a_chat_that_never_subscribed_is_a_no_op(self):
        bd = BotData()
        bd.unsubscribe_from_cs2_patchnotes(101)
        self.assertEqual(bd.cs2_patchnotes_subscribers, set())


if __name__ == "__main__":
    unittest.main()
