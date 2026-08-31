import unittest

from ongabot.cs2.steamid import parse_steam64

VALID = "76561198034202275"


class ParseSteam64Test(unittest.TestCase):
    def test_accepts_a_raw_steam64(self):
        self.assertEqual(parse_steam64(VALID), VALID)

    def test_accepts_a_profiles_url(self):
        self.assertEqual(parse_steam64(f"https://steamcommunity.com/profiles/{VALID}"), VALID)

    def test_accepts_a_profiles_url_with_a_trailing_slash(self):
        self.assertEqual(parse_steam64(f"https://steamcommunity.com/profiles/{VALID}/"), VALID)

    def test_accepts_a_profiles_url_without_a_scheme(self):
        self.assertEqual(parse_steam64(f"steamcommunity.com/profiles/{VALID}"), VALID)

    def test_ignores_surrounding_whitespace(self):
        self.assertEqual(parse_steam64(f"  {VALID}  "), VALID)

    def test_rejects_a_vanity_url(self):
        """Resolving a vanity name needs a Steam Web API key, which this bot deliberately avoids."""
        self.assertIsNone(parse_steam64("https://steamcommunity.com/id/someone"))

    def test_rejects_a_number_below_the_individual_account_range(self):
        self.assertIsNone(parse_steam64("12345678901234567"))

    def test_rejects_a_number_of_the_wrong_length(self):
        self.assertIsNone(parse_steam64("765611980342022"))

    def test_rejects_non_numeric_input(self):
        self.assertIsNone(parse_steam64("not-a-steam-id"))

    def test_rejects_empty_input(self):
        self.assertIsNone(parse_steam64(""))
        self.assertIsNone(parse_steam64(None))


if __name__ == "__main__":
    unittest.main()
