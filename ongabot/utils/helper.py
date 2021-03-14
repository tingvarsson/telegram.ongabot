"""This module contains helper functions."""
from datetime import timedelta

def create_help_text():
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
        "/newevent - Create a new event corresponding to upcoming Wednesday\n"
    )

    return text


def get_upcoming_wednesday_date(today):
    """Get the date of the next upcoming wednesday"""
    wednesday_day_of_week_index = 2  # 0-6, 0 is monday and 6 is sunday
    next_wednesday_date = today + timedelta((wednesday_day_of_week_index - today.weekday()) % 7)
    return next_wednesday_date
