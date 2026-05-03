"""This module contains authorization utilities."""

import os
from typing import Set


def get_bot_admins() -> Set[int]:
    """Parse BOT_ADMINS env var into a set of Telegram user IDs."""
    raw = os.getenv("BOT_ADMINS", "")
    return {int(uid.strip()) for uid in raw.split(",") if uid.strip().isdigit()}
