import tempfile
import unittest
from pathlib import Path

from ongabot.utils.changelog import get_changelog_delta, get_version_entry

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


class GetVersionEntryTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._dir.name)
        self.path = _write_sample(self.tmp)

    def tearDown(self):
        self._dir.cleanup()

    def test_returns_single_version_section(self):
        result = get_version_entry("1.1.0", self.path)
        self.assertIn("1.1.0", result)
        self.assertNotIn("1.2.0", result)
        self.assertNotIn("1.0.0", result)


if __name__ == "__main__":
    unittest.main()
