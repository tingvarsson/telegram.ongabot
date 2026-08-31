"""Render a CS2 session into the MarkdownV2 message ONGAbot posts.

Layout follows utils.points.format_event_recap: a bold underlined heading, then one fenced
code block per match so the columns line up in Telegram's monospace font.

Two rules from Leetify's Developer Guidelines shape this module, and neither is optional:

* every message carries the ATTRIBUTION line and a View-on-Leetify link per match;
* stats are shown exactly as Leetify reports them - kd_ratio is printed, never recomputed
  from kills and deaths, even though both are right there.
"""

import logging
from typing import Iterable, List, Mapping

from telegram import User
from telegram.helpers import escape_markdown

from cs2.session import Cs2Match, Cs2Session
from utils.statistics import NAME_WIDTH, display_names

_logger = logging.getLogger(__name__)

MATCH_URL = "https://leetify.com/app/match-details/{id}"
ATTRIBUTION = "Data Provided by Leetify"

KILLS_WIDTH = 3
DEATHS_WIDTH = 3
KD_WIDTH = 5
MVP_WIDTH = 3


def _header() -> str:
    return (
        "Name".ljust(NAME_WIDTH)
        + " "
        + "K".rjust(KILLS_WIDTH)
        + " "
        + "D".rjust(DEATHS_WIDTH)
        + " "
        + "K/D".rjust(KD_WIDTH)
        + " "
        + "MVP".rjust(MVP_WIDTH)
    )


def _name_cell(name: str) -> str:
    """Truncate/pad to NAME_WIDTH like utils.statistics.format_name_cell.

    Escaping is applied to the whole code block instead of per cell, so this returns raw text
    - see _code_block.
    """
    clean = name.replace("\n", " ").replace("\r", " ")
    return clean[: NAME_WIDTH - 1] + "." if len(clean) > NAME_WIDTH else clean.ljust(NAME_WIDTH)


def _code_block(lines: Iterable[str]) -> str:
    """Wrap table lines in a MarkdownV2 fenced code block."""
    body = "\n".join(lines)
    return "```\n" + escape_markdown(body, version=2, entity_type="pre") + "\n```"


def _match_section(match: Cs2Match, names: Mapping[int, str]) -> List[str]:
    """Heading, scoreboard, and Leetify link for one match."""
    outcome = "W" if match.won else "L"
    heading = escape_markdown(f"{match.map_name} {match.score[0]}-{match.score[1]} ({outcome})", version=2)

    lines = [_header()]
    # Best game first, by the kills Leetify reports.
    for member in sorted(match.members, key=lambda m: m.total_kills, reverse=True):
        name = names.get(member.user_id, member.name)
        lines.append(
            f"{_name_cell(name)} "
            f"{member.total_kills:>{KILLS_WIDTH}} "
            f"{member.total_deaths:>{DEATHS_WIDTH}} "
            f"{member.kd_ratio:>{KD_WIDTH}.2f} "
            f"{member.mvps:>{MVP_WIDTH}}"
        )

    link_url = escape_markdown(MATCH_URL.format(id=match.id), version=2, entity_type="text_link")
    return [f"*{heading}*", _code_block(lines), f"[View on Leetify]({link_url})"]


def format_session(session: Cs2Session, users: Mapping[int, User]) -> str:
    """Format a session into the MarkdownV2 body of the CS2 results message.

    users maps Telegram user id to User, so members are labelled with the same display names
    every other ONGAbot table uses. A member with no User falls back to their in-game name -
    someone can link a Steam account without ever having answered a poll.
    """
    names = display_names(users.values())

    if not session.matches:
        summary = escape_markdown(f"No ONGA matches found for {session.event_date}.", version=2)
        return "\n\n".join(["*__CS2 results__*", summary, f"_{escape_markdown(ATTRIBUTION, version=2)}_"])

    member_count = len(session.played_user_ids)
    summary = escape_markdown(
        f"{len(session.matches)} match{'es' if len(session.matches) != 1 else ''}"
        f" on {session.event_date}, {member_count} of you.",
        version=2,
    )

    sections = ["*__CS2 results__*", summary]
    for match in session.matches:
        sections.extend(_match_section(match, names))
    sections.append(f"_{escape_markdown(ATTRIBUTION, version=2)}_")

    _logger.debug("Rendered CS2 results for %s: %d match(es)", session.event_date, len(session.matches))
    return "\n\n".join(sections)
