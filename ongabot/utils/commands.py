"""Canonical command descriptions and usage strings for all ONGAbot commands.

Handlers import their own USAGE from here; create_help_text() assembles briefs from ALL_COMMANDS.
This module has no imports from bot code, avoiding circular dependencies.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandInfo:
    """
    Simple struct to hold command info for help text and usage instructions.
    """

    command: str
    brief: str  # one-liner shown in /help
    usage: str  # multi-line shown on bad input
    menu_description: str  # short phrase shown in Telegram command menu


HELP = CommandInfo(
    command="help",
    brief="/help - Get some aid in needing times",
    usage="/help",
    menu_description="Get some aid in needing times",
)

CHANGELOG = CommandInfo(
    command="changelog",
    brief="/changelog - Show what changed in the current version",
    usage="/changelog",
    menu_description="Show what changed in the current version",
)

ONGA = CommandInfo(
    command="onga",
    brief="/onga - This is the way, let me show you",
    usage="/onga",
    menu_description="This is the way, let me show you",
)

NEWEVENT = CommandInfo(
    command="newevent",
    brief="/newevent [day=<date|weekday>] [time=<HH:MM>] [slots=<n>] [force=true] - "
    "Create a new event poll (defaults: wednesday, 18:30, 5 slots)",
    usage=(
        "Usage: /newevent [day=<date|weekday>] [time=<HH:MM>] [slots=<n>] [force=true]\n"
        "  day: weekday name (next occurrence), YYYY-MM-DD, or dd.mm.yyyy (default: wednesday)\n"
        "  time: start time of first slot, e.g. 18:30 (default: 18:30)\n"
        "  slots: number of 40-min time slots (default: 5)\n"
        "  force: set to true to replace a cancelled event on the same date\n\n"
        "Examples:\n"
        "  /newevent\n"
        "  /newevent day=friday\n"
        "  /newevent day=friday time=19:00 slots=3\n"
        "  /newevent day=friday force=true"
    ),
    menu_description="Create event poll [day=..] [time=..] [slots=..] [force=..]",
)

CANCELEVENT = CommandInfo(
    command="cancelevent",
    brief="/cancelevent [target_date=<date|weekday>] - Cancel an active event",
    usage=(
        "Usage: /cancelevent [target_date=<date|weekday>]\n"
        "  Specify target_date if multiple events are active.\n"
        "  Accepts: weekday name (next occurrence), YYYY-MM-DD, or dd.mm.yyyy\n\n"
        "Examples:\n"
        "  /cancelevent\n"
        "  /cancelevent target_date=wednesday\n"
        "  /cancelevent target_date=2026-05-10"
    ),
    menu_description="Cancel active event [target_date=..]",
)

UPDATEEVENT = CommandInfo(
    command="updateevent",
    brief="/updateevent [target_date=<date|weekday>] [day=<date|weekday>] [time=<HH:MM>] [slots=<n>]"
    " - Update an active event",
    usage=(
        "Usage: /updateevent [target_date=<date|weekday>] [day=<date|weekday>] [time=<HH:MM>] [slots=<n>]\n"
        "  Unspecified args are unchanged.\n"
        "  target_date: select event by its current date (required if multiple events are active)\n"
        "  day: new event date — weekday name (next occurrence), YYYY-MM-DD, or dd.mm.yyyy\n"
        "  time: new start time, e.g. 20:00\n"
        "  slots: new number of 40-min slots\n"
        "  At least one of day/time/slots must be provided.\n\n"
        "Examples:\n"
        "  /updateevent time=20:00\n"
        "  /updateevent target_date=2026-05-07 day=2026-05-14\n"
        "  /updateevent target_date=2026-05-07 time=20:00 slots=4"
    ),
    menu_description="Update active event [target_date=..] [day=..] [time=..] [slots=..]",
)

SCHEDULE = CommandInfo(
    command="schedule",
    brief="/schedule [trigger_on=<weekday>] [day=<weekday>] [time=<HH:MM>] [slots=<n>]"
    " - Schedule weekly poll creation (defaults: sunday → wednesday, 18:30, 5 slots)",
    usage=(
        "Usage: /schedule [trigger_on=<day>] [day=<day>] [time=<HH:MM>] [slots=<n>]\n"
        "  trigger_on: weekday to trigger poll creation (default: sunday)\n"
        "  day: weekday the poll refers to (default: wednesday)\n"
        "  time: start time of first slot (default: 18:30)\n"
        "  slots: number of 40-min time slots (default: 5)\n\n"
        "Examples:\n"
        "  /schedule\n"
        "  /schedule trigger_on=sunday day=wednesday\n"
        "  /schedule trigger_on=sunday day=wednesday time=19:00 slots=4"
    ),
    menu_description="Schedule weekly polls [trigger_on=..] [day=..] [time=..] [slots=..]",
)

RESCHEDULE = CommandInfo(
    command="reschedule",
    brief="/reschedule [trigger_on=<weekday>] [day=<weekday>] [time=<HH:MM>] [slots=<n>] - Update the weekly schedule",
    usage=(
        "Usage: /reschedule [trigger_on=<day>] [day=<day>] [time=<HH:MM>] [slots=<n>]\n"
        "  Unspecified args inherit from the current schedule.\n"
        "  trigger_on: weekday to trigger poll creation\n"
        "  day: weekday the poll refers to\n"
        "  time: start time of first slot\n"
        "  slots: number of 40-min time slots\n\n"
        "Examples:\n"
        "  /reschedule time=20:00\n"
        "  /reschedule trigger_on=monday day=thursday"
    ),
    menu_description="Update weekly schedule [trigger_on=..] [day=..] [time=..] [slots=..]",
)

DESCHEDULE = CommandInfo(
    command="deschedule",
    brief="/deschedule - Remove the weekly schedule",
    usage="/deschedule",
    menu_description="Remove the weekly schedule",
)

AUTHORIZE = CommandInfo(
    command="authorize",
    brief="/authorize - Authorize this chat to use ONGAbot (bot admins only)",
    usage="/authorize",
    menu_description="Authorize this chat (admins only)",
)

DEAUTHORIZE = CommandInfo(
    command="deauthorize",
    brief="/deauthorize - Deauthorize this chat from using ONGAbot (bot admins only)",
    usage="/deauthorize",
    menu_description="Deauthorize this chat (admins only)",
)

BOT_SHORT_DESCRIPTION = "ONGAbot - the only bot you'll ever need"

BOT_DESCRIPTION = (
    "ONGAbot helps group chats organize recurring events with Telegram polls. "
    "Create event polls, manage weekly schedules, and track participation — "
    "all without leaving your chat."
)

# Ordered for help text assembly
ALL_COMMANDS = [
    HELP,
    CHANGELOG,
    ONGA,
    NEWEVENT,
    CANCELEVENT,
    UPDATEEVENT,
    SCHEDULE,
    RESCHEDULE,
    DESCHEDULE,
    AUTHORIZE,
    DEAUTHORIZE,
]
