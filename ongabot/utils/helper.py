"""This module contains helper functions."""

from datetime import date, timedelta


def create_help_text() -> str:
    """Print the help text for a /start or /help command"""
    text = (
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
        "/help - Get some aid in needing times\n"
        "/onga - This is the way, let me show you\n"
        "/newevent - Create a new event corresponding to upcoming Wednesday and pins it\n"
        "/cancelevent - Cancels the latest default event, i.e. unpins it\n"
        "/schedule <day>[OPTIONAL] - Schedules a job to create a poll on "
        "every upcoming <day>. If no argument is supplied, job"
        " is scheduled to run on sundays\n"
        "/deschedule - Deschedules jobs"
    )

    return text


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
