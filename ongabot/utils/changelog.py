"""Utilities for reading and parsing CHANGELOG.md."""

import logging
import os
import re
from pathlib import Path
from typing import Optional

_logger = logging.getLogger(__name__)

# In the container: CHANGELOG.md is copied to /ongabot/ (same dir as the code), two levels up from utils/.
# For local dev outside Docker, override with the CHANGELOG_PATH env var pointing to the repo-root file.
CHANGELOG_PATH = Path(os.getenv("CHANGELOG_PATH", str(Path(__file__).parent.parent / "CHANGELOG.md")))

_VERSION_HEADER_RE = re.compile(r"^## \[([^\]]+)\]", re.MULTILINE)


def get_changelog_delta(
    old_version: Optional[str],
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

    # Resolve old_version boundary; fall back to next entry if old_version unknown
    old_idx: Optional[int] = None
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


def get_version_entry(version: str, changelog_path: Path = CHANGELOG_PATH) -> str:
    """Return the changelog entry for a single version."""
    return get_changelog_delta(None, version, changelog_path)
