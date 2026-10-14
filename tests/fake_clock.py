"""Give a MagicMock chat the zone-aware clock a real Chat has.

Job callbacks ask the chat for its tz, now(), today() and is_quiet(); a bare MagicMock would
answer with more mocks, which cannot be compared with real dates.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

UTC = ZoneInfo("UTC")


def with_clock(chat, tz: ZoneInfo = UTC):
    """Set tz, now() and today() on the mock chat, reading the real clock in tz.

    is_quiet() answers False, so a send passes a real bool rather than a truthy mock; a test
    of quiet hours sets it to True itself.
    """
    chat.tz = tz
    chat.now.side_effect = lambda: datetime.now(tz)
    chat.today.side_effect = lambda: datetime.now(tz).date()
    chat.is_quiet.return_value = False
    return chat
