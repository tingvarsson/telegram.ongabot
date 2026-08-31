import re
import tempfile
import unittest
from pathlib import Path

from ongabot.utils.changelog import (
    MAX_MESSAGE_CHARS,
    get_changelog,
    get_changelog_delta,
    is_dev_version,
    split_for_telegram,
)

SAMPLE = """\
# Changelog

## [Unreleased]

## [1.2.0] - 2026-05-24

### Fixed

- Big fix

## [1.1.0] - 2026-05-01

### Added

- New feature

## [1.0.0] - 2026-01-01

### Added

- Initial release

[Unreleased]: https://github.com/tingvarsson/telegram.ongabot/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/tingvarsson/telegram.ongabot/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/tingvarsson/telegram.ongabot/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/tingvarsson/telegram.ongabot/releases/tag/v1.0.0
"""


def _write_sample(tmp: Path) -> Path:
    p = tmp / "CHANGELOG.md"
    p.write_text(SAMPLE)
    return p


class GetChangelogDeltaTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._dir.name)
        self.path = _write_sample(self.tmp)

    def tearDown(self):
        self._dir.cleanup()

    def test_none_old_version_returns_only_new_entry(self):
        result = get_changelog_delta(None, "1.2.0", self.path)
        self.assertIn("1.2.0", result)
        self.assertNotIn("1.1.0", result)
        self.assertNotIn("1.0.0", result)

    def test_adjacent_versions_returns_new_entry_only(self):
        result = get_changelog_delta("1.1.0", "1.2.0", self.path)
        self.assertIn("1.2.0", result)
        self.assertNotIn("1.1.0", result)

    def test_two_version_gap_returns_both_entries(self):
        result = get_changelog_delta("1.0.0", "1.2.0", self.path)
        self.assertIn("1.2.0", result)
        self.assertIn("1.1.0", result)
        self.assertNotIn("1.0.0", result)

    def test_unknown_new_version_returns_fallback(self):
        result = get_changelog_delta(None, "9.9.9", self.path)
        self.assertIn("9.9.9", result)

    def test_unknown_old_version_returns_new_entry_only(self):
        # Unknown old version falls back to showing just new entry
        result = get_changelog_delta("0.0.0", "1.2.0", self.path)
        self.assertIn("1.2.0", result)
        self.assertNotIn("1.1.0", result)

    def test_missing_file_returns_fallback(self):
        missing = self.tmp / "no_such_file.md"
        result = get_changelog_delta(None, "1.2.0", missing)
        self.assertIn("1.2.0", result)

    def test_unreleased_section_excluded_from_adjacent_entry(self):
        result = get_changelog_delta(None, "1.2.0", self.path)
        self.assertNotIn("Unreleased", result)

    def test_oldest_version_is_last_in_file_returns_full_entry(self):
        result = get_changelog_delta(None, "1.0.0", self.path)
        self.assertIn("1.0.0", result)
        self.assertNotIn("1.1.0", result)

    def test_oldest_version_excludes_trailing_link_reference_block(self):
        # 1.0.0 is both the "new" and only version reachable, so the slice
        # runs to EOF and must not swallow the trailing link-reference block.
        result = get_changelog_delta(None, "1.0.0", self.path)
        self.assertNotIn("http", result)
        self.assertNotIn("]: ", result)


class IsDevVersionTest(unittest.TestCase):
    def test_clean_release_is_not_dev(self):
        self.assertFalse(is_dev_version("1.2.0"))

    def test_plus_dev_suffix_is_dev(self):
        self.assertTrue(is_dev_version("1.2.0+dev"))

    def test_hyphen_suffix_is_dev(self):
        self.assertTrue(is_dev_version("1.2.0-rc1"))

    def test_non_semver_is_dev(self):
        self.assertTrue(is_dev_version("nightly"))


class GetChangelogTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._dir.name)
        self.path = _write_sample(self.tmp)

    def tearDown(self):
        self._dir.cleanup()

    def test_dev_build_shows_unreleased(self):
        result = get_changelog("1.2.0+dev", 1, self.path)
        self.assertIn("Unreleased", result)
        self.assertNotIn("1.2.0", result)

    def test_release_build_shows_its_section(self):
        result = get_changelog("1.2.0", 1, self.path)
        self.assertIn("1.2.0", result)
        self.assertNotIn("Unreleased", result)
        self.assertNotIn("1.1.0", result)

    def test_dev_build_count_includes_unreleased_and_releases(self):
        result = get_changelog("1.2.0+dev", 3, self.path)
        self.assertIn("Unreleased", result)
        self.assertIn("1.2.0", result)
        self.assertIn("1.1.0", result)
        self.assertNotIn("1.0.0", result)

    def test_release_build_count_walks_downward(self):
        result = get_changelog("1.2.0", 2, self.path)
        self.assertIn("1.2.0", result)
        self.assertIn("1.1.0", result)
        self.assertNotIn("1.0.0", result)

    def test_count_larger_than_history_stops_at_end(self):
        result = get_changelog("1.0.0", 5, self.path)
        self.assertIn("1.0.0", result)

    def test_oldest_section_excludes_trailing_link_reference_block(self):
        # Reaching the last section in the file means the slice runs to EOF;
        # the trailing link-reference block must not leak into the output.
        result = get_changelog("1.0.0", 1, self.path)
        self.assertIn("Initial release", result)
        self.assertNotIn("http", result)
        self.assertNotIn("]: ", result)

    def test_count_below_one_treated_as_one(self):
        result = get_changelog("1.2.0", 0, self.path)
        self.assertIn("1.2.0", result)
        self.assertNotIn("1.1.0", result)

    def test_missing_file_returns_fallback(self):
        missing = self.tmp / "no_such_file.md"
        result = get_changelog("1.2.0", 1, missing)
        self.assertIn("1.2.0", result)

    def test_unknown_release_version_returns_fallback(self):
        result = get_changelog("9.9.9", 1, self.path)
        self.assertIn("9.9.9", result)


class RealChangelogTest(unittest.TestCase):
    real_path = Path(__file__).resolve().parent.parent / "CHANGELOG.md"

    def _oldest_release(self):
        content = self.real_path.read_text(encoding="utf-8")
        versions = re.findall(r"^## \[([^\]]+)\]", content, re.MULTILINE)
        releases = [v for v in versions if re.fullmatch(r"\d+\.\d+\.\d+", v)]
        self.assertTrue(releases, "no release headers found in real CHANGELOG.md")
        return releases[-1]

    def test_full_range_excludes_link_reference_block(self):
        oldest = self._oldest_release()
        result = get_changelog(oldest, 99, self.real_path)
        self.assertIn(oldest, result)
        self.assertNotIn("http", result)
        self.assertNotIn("]: ", result)

    def test_delta_to_oldest_excludes_link_reference_block(self):
        oldest = self._oldest_release()
        result = get_changelog_delta(None, oldest, self.real_path)
        self.assertNotIn("http", result)
        self.assertNotIn("]: ", result)

    def test_every_entry_fits_in_a_single_telegram_message(self):
        """A single /changelog entry that needs splitting is an entry nobody will read."""
        content = self.real_path.read_text(encoding="utf-8")
        for version in re.findall(r"^## \[(\d+\.\d+\.\d+)\]", content, re.MULTILINE):
            entry = get_changelog(version, 1, self.real_path)
            self.assertLessEqual(
                len(entry),
                MAX_MESSAGE_CHARS,
                f"changelog entry {version} is {len(entry)} chars - trim it",
            )


class SplitForTelegramTest(unittest.TestCase):
    def test_short_text_is_left_alone(self):
        self.assertEqual(split_for_telegram("short"), ["short"])

    def test_long_text_is_split_into_messages_that_fit(self):
        text = "\n\n".join(["paragraph " * 20] * 60)

        chunks = split_for_telegram(text)

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), MAX_MESSAGE_CHARS)

    def test_splits_on_paragraph_boundaries(self):
        text = "\n\n".join(f"paragraph {i} " + "x" * 100 for i in range(60))

        chunks = split_for_telegram(text, limit=500)

        for chunk in chunks:
            self.assertTrue(chunk.startswith("paragraph"), f"chunk starts mid-paragraph: {chunk[:40]!r}")

    def test_falls_back_to_line_breaks_when_there_are_no_blank_lines(self):
        text = "\n".join("x" * 50 for _ in range(40))

        chunks = split_for_telegram(text, limit=200)

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertTrue(all(len(line) == 50 for line in chunk.splitlines()), "a line was cut in half")

    def test_a_single_oversized_paragraph_is_hard_sliced_rather_than_dropped(self):
        text = "x" * 500

        chunks = split_for_telegram(text, limit=200)

        self.assertEqual("".join(chunks), text)

    def test_nothing_is_lost_in_the_split(self):
        text = "\n\n".join(f"paragraph {i}" for i in range(500))

        self.assertEqual("\n\n".join(split_for_telegram(text, limit=300)), text)


if __name__ == "__main__":
    unittest.main()
