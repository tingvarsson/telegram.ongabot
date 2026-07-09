import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.version as version_script
from ongabot._version import __version__
from ongabot.utils.changelog import is_dev_version

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "version.py"


def _run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


class VersionScriptCliTest(unittest.TestCase):
    def test_full_is_single_line_starting_with_semver(self):
        result = _run()
        self.assertEqual(result.returncode, 0)
        out = result.stdout.strip()
        self.assertEqual(len(out.splitlines()), 1)
        self.assertRegex(out, r"^\d+\.\d+\.\d+")

    def test_base_is_clean_semver_single_line(self):
        result = _run("--base")
        self.assertEqual(result.returncode, 0)
        out = result.stdout.strip()
        self.assertEqual(len(out.splitlines()), 1)
        self.assertRegex(out, r"^\d+\.\d+\.\d+$")

    def test_is_dev_exit_code_matches_runtime_rule(self):
        result = _run("--is-dev")
        expected = 0 if is_dev_version(__version__) else 1
        self.assertEqual(result.returncode, expected)


class VersionScriptUnitTest(unittest.TestCase):
    def test_base_strips_dev_suffix(self):
        with patch.object(version_script, "__version__", "1.3.0+dev"):
            self.assertEqual(version_script.base_version(), "1.3.0")

    def test_base_of_clean_release(self):
        with patch.object(version_script, "__version__", "1.3.0"):
            self.assertEqual(version_script.base_version(), "1.3.0")

    def test_is_dev_true_for_suffix_false_for_clean(self):
        with patch.object(version_script, "__version__", "1.3.0+dev"):
            self.assertTrue(version_script.is_dev())
        with patch.object(version_script, "__version__", "1.3.0"):
            self.assertFalse(version_script.is_dev())


if __name__ == "__main__":
    unittest.main()
