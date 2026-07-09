#!/usr/bin/env python3
"""Print or classify the ONGAbot version.

Single source of truth for version/dev-build logic outside the Python runtime.
The Makefile and CI workflows call this instead of parsing ongabot/_version.py
with ad-hoc regexes.

Usage:
    python scripts/version.py            # full version, e.g. 1.2.0+dev
    python scripts/version.py --base     # X.Y.Z with any suffix stripped
    python scripts/version.py --is-dev   # exit 0 if a development build, else exit 1
"""

import argparse
import re
import sys
from pathlib import Path

# Make the repo root importable so this runs in bare CI without `pip install`.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ongabot._version import __version__  # noqa: E402
from ongabot.utils.changelog import is_dev_version  # noqa: E402


def full_version() -> str:
    """Return the full version string, e.g. '1.2.0+dev'."""
    return __version__


def base_version() -> str:
    """Return the clean X.Y.Z base, stripping any pre-release/build suffix."""
    match = re.match(r"\d+\.\d+\.\d+", __version__)
    if not match:
        raise ValueError(f"Cannot parse base version from {__version__!r}")
    return match.group(0)


def is_dev() -> bool:
    """Return True if the current build is a development build."""
    return is_dev_version(__version__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print or classify the ONGAbot version.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--base", action="store_true", help="print X.Y.Z with any suffix stripped")
    group.add_argument("--is-dev", action="store_true", help="exit 0 if a development build, else 1")
    group.add_argument("--full", action="store_true", help="print the full version (default)")
    args = parser.parse_args(argv)

    if args.is_dev:
        return 0 if is_dev() else 1
    if args.base:
        print(base_version())
        return 0
    print(full_version())
    return 0


if __name__ == "__main__":
    sys.exit(main())
