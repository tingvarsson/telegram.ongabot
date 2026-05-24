#!/usr/bin/env python3
"""Update CHANGELOG.md when cutting a release.

Usage: python scripts/update_changelog.py NEW_VERSION

Converts the [Unreleased] section to [NEW_VERSION] - DATE, inserts a fresh
empty [Unreleased] section at the top, and updates the comparison links.
"""

import datetime
import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).parent.parent / "CHANGELOG.md"

UNRELEASED_HEADER = "## [Unreleased]"
UNRELEASED_LINK_RE = re.compile(
    r"^\[Unreleased\]: (https://github\.com/[^/]+/[^/]+/compare/)v(.+)\.\.\.HEAD$",
    re.MULTILINE,
)


def update_changelog(new_version: str) -> None:
    today = datetime.date.today().isoformat()
    content = CHANGELOG.read_text()

    # Replace ## [Unreleased] with new version header, prepend fresh [Unreleased]
    new_header = f"{UNRELEASED_HEADER}\n\n## [{new_version}] - {today}"
    if UNRELEASED_HEADER not in content:
        print(f"ERROR: '{UNRELEASED_HEADER}' not found in {CHANGELOG}", file=sys.stderr)
        sys.exit(1)
    content = content.replace(UNRELEASED_HEADER, new_header, 1)

    # Update comparison links at the bottom
    match = UNRELEASED_LINK_RE.search(content)
    if not match:
        print("ERROR: [Unreleased] comparison link not found in CHANGELOG", file=sys.stderr)
        sys.exit(1)

    base_url = match.group(1)
    prev_version = match.group(2)

    new_unreleased_link = f"[Unreleased]: {base_url}v{new_version}...HEAD"
    new_version_link = f"[{new_version}]: {base_url}v{prev_version}...v{new_version}"

    content = UNRELEASED_LINK_RE.sub(
        f"{new_unreleased_link}\n{new_version_link}",
        content,
    )

    CHANGELOG.write_text(content)
    print(f"Updated {CHANGELOG} for v{new_version}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} NEW_VERSION", file=sys.stderr)
        sys.exit(1)
    update_changelog(sys.argv[1])
