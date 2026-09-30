"""The bot's time source: the bot-wide default zone and zone lookup."""

import os
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from ongabot.utils import clock


class BotTimezoneTest(unittest.TestCase):
    def test_defaults_to_utc_when_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(clock.bot_timezone(), ZoneInfo("UTC"))

    def test_reads_the_env_var(self):
        with patch.dict(os.environ, {"BOT_TIMEZONE": "Europe/Stockholm"}):
            self.assertEqual(clock.bot_timezone(), ZoneInfo("Europe/Stockholm"))

    def test_unknown_zone_warns_and_falls_back_to_utc(self):
        with patch.dict(os.environ, {"BOT_TIMEZONE": "Mars/Olympus_Mons"}):
            with self.assertLogs("ongabot.utils.clock", level="WARNING"):
                self.assertEqual(clock.bot_timezone(), ZoneInfo("UTC"))


class ResolveTimezoneTest(unittest.TestCase):
    def test_ignores_case_and_returns_the_canonical_name(self):
        self.assertEqual(str(clock.resolve_timezone("europe/STOCKHOLM")), "Europe/Stockholm")

    def test_rejects_unknown_names(self):
        for name in ("Nowhere/Special", "", "../../etc/passwd", "/etc/localtime"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                clock.resolve_timezone(name)


class NowTest(unittest.TestCase):
    def test_now_is_aware_in_the_given_zone(self):
        tokyo = ZoneInfo("Asia/Tokyo")
        self.assertEqual(clock.now(tokyo).tzinfo, tokyo)
        self.assertEqual(clock.today(tokyo), clock.now(tokyo).date())


if __name__ == "__main__":
    unittest.main()
