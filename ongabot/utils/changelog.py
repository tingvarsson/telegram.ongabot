"""Utilities for reading and parsing CHANGELOG.md."""

import logging
import os
import re
from pathlib import Path

_logger = logging.getLogger(__name__)

# In the container: CHANGELOG.md is copied to /ongabot/ (same dir as the code), two levels up from utils/.
# For local dev outside Docker, override with the CHANGELOG_PATH env var pointing to the repo-root file.
CHANGELOG_PATH = Path(os.getenv("CHANGELOG_PATH", str(Path(__file__).parent.parent / "CHANGELOG.md")))

_VERSION_HEADER_RE = re.compile(r"^## \[([^\]]+)\]", re.MULTILINE)

# A clean release version is exactly MAJOR.MINOR.PATCH. Anything else (e.g. a
# "1.2.0+dev" build-metadata suffix) marks a development build.
_RELEASE_VERSION_RE = re.compile(r"\d+\.\d+\.\d+")


def is_dev_version(version: str) -> bool:
    """Return True if version is a development build (not a clean X.Y.Z release)."""
    return _RELEASE_VERSION_RE.fullmatch(version) is None


def get_changelog_delta(
    old_version: str | None,
    new_version: str,
    changelog_path: Path = CHANGELOG_PATH,
) -> str:
    """Return changelog text covering new_version down to (not including) old_version.

    If old_version is None or not found in the file, returns only the new_version entry.
    Returns a plain-text fallback if the file is missing or the version is not found.
    """
    try:
        content = changelog_path.read_text(encoding="utf-8")
    except OSError as e:
        _logger.error("Failed to read changelog at %s: %s", changelog_path, e)
        return f"ONGAbot updated to v{new_version}. (Changelog unavailable)"

    matches = list(_VERSION_HEADER_RE.finditer(content))
    versions = [m.group(1) for m in matches]

    try:
        new_idx = versions.index(new_version)
    except ValueError:
        _logger.warning("Version %s not found in changelog", new_version)
        return f"ONGAbot updated to v{new_version}. (No changelog entry found)"

    # Guard: same version produces empty delta
    if old_version is not None and old_version == new_version:
        _logger.warning("get_changelog_delta called with same old and new version: %s", new_version)
        return ""

    # Resolve old_version boundary; fall back to next entry if old_version unknown
    old_idx: int | None = None
    if old_version is not None:
        try:
            old_idx = versions.index(old_version)
        except ValueError:
            _logger.warning(
                "Previous version %s not found in changelog; showing only %s entry",
                old_version,
                new_version,
            )

    start_pos = matches[new_idx].start()
    if old_idx is not None:
        end_pos = matches[old_idx].start()
    elif new_idx + 1 < len(matches):
        end_pos = matches[new_idx + 1].start()
    else:
        end_pos = len(content)

    return content[start_pos:end_pos].strip()


def get_changelog(version: str, count: int = 1, changelog_path: Path = CHANGELOG_PATH) -> str:
    """Return the current changelog section plus the next count-1 sections below it.

    The starting section is [Unreleased] for a development build (is_dev_version),
    otherwise the section whose header matches the release version. count counts
    sections including [Unreleased]; values below 1 are treated as 1. Returns a
    plain-text fallback if the file is missing or the starting section is absent.
    """
    try:
        content = changelog_path.read_text(encoding="utf-8")
    except OSError as e:
        _logger.error("Failed to read changelog at %s: %s", changelog_path, e)
        return f"ONGAbot v{version}. (Changelog unavailable)"

    matches = list(_VERSION_HEADER_RE.finditer(content))
    versions = [m.group(1) for m in matches]

    start_header = "Unreleased" if is_dev_version(version) else version
    try:
        start_idx = versions.index(start_header)
    except ValueError:
        _logger.warning("Changelog section %s not found", start_header)
        return f"ONGAbot v{version}. (No changelog entry found)"

    count = max(1, count)
    end_section_idx = start_idx + count  # exclusive index into matches
    start_pos = matches[start_idx].start()
    end_pos = matches[end_section_idx].start() if end_section_idx < len(matches) else len(content)

    return content[start_pos:end_pos].strip()
