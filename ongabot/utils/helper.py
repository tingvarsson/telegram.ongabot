"""This module contains helper functions."""

from datetime import date, datetime, time, timedelta

from .commands import ALL_COMMANDS
from _version import __version__


def create_help_text() -> str:
    """Print the help text for a /start or /help command"""
    header = (
        "Welcome traveler, my name is ONGAbot.\n"
        "I'm the one and only, the truth speaker.\n"
        "\n"
        "My duties are:\n"
        " - Uphold the law, obviously, with weekly ON/GA polls\n"
        " - Give praise to the faithful\n"
        " - Aid the needing\n"
        " - Condemn the wicked\n"
        "\n"
        "Commandments:\n"
    )
    commands = "\n".join(cmd.brief for cmd in ALL_COMMANDS)
    return f"{header}{commands}\n\nVersion: {__version__}"


def get_upcoming_date(today: date, upcoming_weekday: str) -> date:
    """Get the date of the next upcoming day with name upcoming_weekday"""
    index = get_weekday_index_from_name(upcoming_weekday)

    next_date = today + timedelta((index - today.weekday()) % 7)
    return next_date


def is_valid_weekday(day: str) -> bool:
    """Validates that the supplied arg is a valid day"""
    if day.lower() not in [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]:
        return False
    return True


def get_weekday_index_from_name(day_name: str) -> int:
    """Get the day index from week day name"""
    return {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }[day_name.lower()]


def parse_date(token: str) -> date:
    """
    Parse a day-or-date token into a concrete date.

    Accepts weekday names ("wednesday"), ISO dates ("2026-05-10"), or dd.mm.yyyy dates.
    Returns the next upcoming occurrence for weekday names.
    Raises ValueError if the token cannot be parsed.
    """
    if is_valid_weekday(token):
        return get_upcoming_date(date.today(), token.lower())
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(token, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date from: {token!r}. Use a weekday name, YYYY-MM-DD, or dd.mm.yyyy.")


def parse_time(token: str) -> time:
    """
    Parse a HH:MM string into a datetime.time.
    Raises ValueError if the format is wrong.
    """
    try:
        return datetime.strptime(token, "%H:%M").time()
    except ValueError as e:
        raise ValueError(f"Cannot parse time from: {token!r}. Use HH:MM format (e.g. 18:30).") from e


def parse_num_slots(value: str) -> int:
    """Parse and validate a number-of-slots value. Raises ValueError if not a positive integer."""
    try:
        num = int(value)
    except ValueError as e:
        raise ValueError(f"slots must be a positive integer, got: {value!r}") from e
    if num < 1:
        raise ValueError(f"slots must be a positive integer, got: {value!r}")
    return num


def parse_event_job_args(
    args: list[str],
    trigger_on: str,
    event_day: str,
    start_time: time,
    num_slots: int,
) -> tuple[str, str, time, int]:
    """Parse trigger_on/day/time/slots args for schedule/reschedule commands, using supplied values as defaults.

    Raises ValueError on invalid input.
    """
    named = parse_named_args(args, {"trigger_on", "day", "time", "slots"})
    if "trigger_on" in named:
        if not is_valid_weekday(named["trigger_on"]):
            raise ValueError(f"Invalid weekday: {named['trigger_on']!r}")
        trigger_on = named["trigger_on"].lower()
    if "day" in named:
        if not is_valid_weekday(named["day"]):
            raise ValueError(f"Invalid weekday: {named['day']!r}")
        event_day = named["day"].lower()
    if "time" in named:
        start_time = parse_time(named["time"])
    if "slots" in named:
        num_slots = parse_num_slots(named["slots"])
    return trigger_on, event_day, start_time, num_slots


def parse_named_args(args: list[str], allowed_keys: set[str]) -> dict[str, str]:
    """
    Parse a list of key=value argument strings, validating keys against an allowed set.

    Raises ValueError if any arg is not key=value, or if a key is not in allowed_keys.
    """
    result: dict[str, str] = {}
    for arg in args:
        if "=" not in arg:
            raise ValueError(f"Expected key=value format, got: {arg!r}")
        key, _, value = arg.partition("=")
        if key.lower() not in allowed_keys:
            known = ", ".join(sorted(allowed_keys))
            raise ValueError(f"Unknown argument key: {key!r}. Known keys: {known}")
        result[key.lower()] = value
    return result
