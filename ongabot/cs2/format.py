"""Render a CS2 session into the MarkdownV2 message ONGAbot posts.

Layout follows utils.points.format_event_recap: a bold underlined heading, then fenced code
blocks so the columns line up in Telegram's monospace font. The message reads top-down as
the night did - what happened overall, how each member did across it, then match by match.

Two rules from Leetify's Developer Guidelines shape this module, and neither is optional:

* every message carries the ATTRIBUTION line and a View-on-Leetify link per match;
* per-match stats are shown exactly as Leetify reports them - kd_ratio is printed, never
  recomputed from kills and deaths, even though both are right there.

The one derived value is the session table's combined K/D, which Leetify does not supply per
session. Its inputs (total_kills, total_deaths) are raw Valve counts rather than Leetify
metrics, and it is the number people actually want out of a night.
"""

import logging
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from telegram import User
from telegram.helpers import escape_markdown

from cs2.session import Cs2Match, Cs2Session, PlayerLine
from utils.statistics import NAME_WIDTH, display_names, fit_name

_logger = logging.getLogger(__name__)

MATCH_URL = "https://leetify.com/app/match-details/{id}"
ATTRIBUTION = "Data Provided by Leetify"

# Telegram rejects a message over 4096 characters outright, so a long night is trimmed
# rather than lost. The margin absorbs the "not shown" note appended after trimming.
MAX_MESSAGE_CHARS = 4096
TRIM_MARGIN_CHARS = 200

MEMBER_MARK = "* "  # prefix marking a linked member; two spaces for everyone else
MARK_WIDTH = len(MEMBER_MARK)
KILLS_WIDTH = 3
DEATHS_WIDTH = 3
KD_WIDTH = 5
MVP_WIDTH = 3
MATCHES_WIDTH = 3
TEAM_DIVIDER = "--"


def _name_cell(name: str, fallback: str = "?") -> str:
    """Pad/truncate a name to NAME_WIDTH monospace columns.

    Delegates to utils.statistics.fit_name, which measures display columns rather than code
    points - in-game names are full of emoji and CJK, and len() would shift the whole row.
    Escaping is applied to the whole code block rather than per cell, so this returns raw
    text; see _code_block.
    """
    return fit_name(name, NAME_WIDTH, fallback)


def _code_block(lines: Iterable[str]) -> str:
    """Wrap table lines in a MarkdownV2 fenced code block."""
    body = "\n".join(lines)
    return "```\n" + escape_markdown(body, version=2, entity_type="pre") + "\n```"


def _kd(kills: int, deaths: int) -> str:
    """Combined K/D over a session, or "-" when a member has not died yet."""
    return f"{kills / deaths:.2f}" if deaths else "-"


def _summary_line(session: Cs2Session) -> str:
    """One plain-text line: how many matches, how they went, and whether any went to OT."""
    matches = session.matches
    tally: Dict[str, int] = {"W": 0, "L": 0, "D": 0}
    for match in matches:
        tally[match.outcome] += 1

    parts = [f"{len(matches)} match{'es' if len(matches) != 1 else ''}"]
    # Draws are rare (competitive only, at 12-12), so the clause is dropped when there are none.
    record = " ".join(f"{tally[key]}{key}" for key in ("W", "L", "D") if tally[key])
    if record:
        parts.append(record)
    overtime = sum(1 for match in matches if match.overtime)
    if overtime:
        parts.append(f"{overtime} OT")
    return " · ".join(parts)


def _session_table(session: Cs2Session, names: Mapping[int, str]) -> Optional[str]:
    """Each linked member's night, combined across every match they appear in."""
    totals: Dict[int, List[int]] = {}  # user_id -> [matches, kills, deaths, mvps]
    for match in session.matches:
        for member in match.members:
            row = totals.setdefault(member.user_id, [0, 0, 0, 0])
            row[0] += 1
            row[1] += member.total_kills
            row[2] += member.total_deaths
            row[3] += member.mvps

    if not totals:
        return None

    header = (
        "Name".ljust(NAME_WIDTH)
        + " "
        + "M".rjust(MATCHES_WIDTH)
        + " "
        + "K".rjust(KILLS_WIDTH)
        + " "
        + "D".rjust(DEATHS_WIDTH)
        + " "
        + "K/D".rjust(KD_WIDTH)
    )
    lines = [header]
    for user_id, (played, kills, deaths, _mvps) in sorted(totals.items(), key=lambda item: item[1][1], reverse=True):
        lines.append(
            f"{_name_cell(names.get(user_id, str(user_id)))} "
            f"{played:>{MATCHES_WIDTH}} "
            f"{kills:>{KILLS_WIDTH}} "
            f"{deaths:>{DEATHS_WIDTH}} "
            f"{_kd(kills, deaths):>{KD_WIDTH}}"
        )
    return _code_block(lines)


def _player_row(player: PlayerLine, names: Mapping[int, str]) -> str:
    """One scoreboard line. Members are marked and use their Telegram display name."""
    if player.is_member:
        label = names.get(player.user_id, player.name)
        mark = MEMBER_MARK
    else:
        # Everyone else in the lobby is a stranger; their in-game name is all we have.
        label = player.name
        mark = " " * MARK_WIDTH
    # An all-emoji name sanitizes to nothing, so fall back to the tail of the Steam64 -
    # short, aligned, and still tells two such players apart.
    return (
        f"{mark}{_name_cell(label, fallback=f'#{player.steam64_id[-4:]}')} "
        f"{player.total_kills:>{KILLS_WIDTH}} "
        f"{player.total_deaths:>{DEATHS_WIDTH}} "
        f"{player.kd_ratio:>{KD_WIDTH}.2f} "
        f"{player.mvps:>{MVP_WIDTH}}"
    )


def _sorted_side(players: Sequence[PlayerLine]) -> List[PlayerLine]:
    """A side's players, best game first by the kills Leetify reports."""
    return sorted(players, key=lambda player: player.total_kills, reverse=True)


def _match_heading(match: Cs2Match) -> str:
    """Map, score, outcome and - when the timestamp parsed - when the match ended."""
    text = f"{match.map_name} {match.score[0]}-{match.score[1]} ({match.outcome})"
    if match.overtime:
        text += " OT"
    if match.finished_at is not None:
        text += f" · ended {match.finished_at.strftime('%H:%M')}"
    return f"*{escape_markdown(text, version=2)}*"


def _match_section(match: Cs2Match, names: Mapping[int, str]) -> List[str]:
    """Heading, full ten-player scoreboard split by side, and the Leetify link."""
    header = (
        " " * MARK_WIDTH
        + "Name".ljust(NAME_WIDTH)
        + " "
        + "K".rjust(KILLS_WIDTH)
        + " "
        + "D".rjust(DEATHS_WIDTH)
        + " "
        + "K/D".rjust(KD_WIDTH)
        + " "
        + "MVP".rjust(MVP_WIDTH)
    )
    ours = [player for player in match.players if player.team_number == match.our_team]
    theirs = [player for player in match.players if player.team_number != match.our_team]

    lines = [header]
    lines += [_player_row(player, names) for player in _sorted_side(ours)]
    if theirs:
        lines.append(" " * MARK_WIDTH + TEAM_DIVIDER)
        lines += [_player_row(player, names) for player in _sorted_side(theirs)]

    link_url = escape_markdown(MATCH_URL.format(id=match.id), version=2, entity_type="text_link")
    return [_match_heading(match), _code_block(lines), f"[View on Leetify]({link_url})"]


def _trim_to_limit(head: List[str], sections: List[List[str]], tail: List[str]) -> Tuple[List[str], int]:
    """Drop whole match sections, oldest first, until the message fits.

    Trimming by measurement rather than a fixed match cap, because in-game names vary in
    length and a fixed cap would be either wasteful or occasionally still too long.
    """
    kept = list(sections)
    dropped = 0
    while kept:
        body = head + [line for section in kept for line in section] + tail
        if len("\n\n".join(body)) <= MAX_MESSAGE_CHARS - TRIM_MARGIN_CHARS:
            break
        kept.pop(0)  # sections are chronological, so the oldest match goes first
        dropped += 1

    body = head + [line for section in kept for line in section]
    if dropped:
        note = escape_markdown(f"… and {dropped} earlier match{'es' if dropped != 1 else ''} not shown.", version=2)
        body.append(f"_{note}_")
        _logger.info("Trimmed %d match section(s) to fit Telegram's message limit", dropped)
    return body + tail, dropped


def format_session(session: Cs2Session, users: Mapping[int, User]) -> str:
    """Format a session into the MarkdownV2 body of the CS2 results message.

    users maps Telegram user id to User, so members are labelled with the same display names
    every other ONGAbot table uses. A member with no User falls back to their in-game name -
    someone can link a Steam account without ever having answered a poll.
    """
    names = display_names(users.values())
    heading = f"*__CS2 results · {escape_markdown(str(session.event_date), version=2)}__*"
    attribution = f"_{escape_markdown(ATTRIBUTION, version=2)}_"

    if not session.matches:
        summary = escape_markdown(f"No ONGA matches found for {session.event_date}.", version=2)
        return "\n\n".join([heading, summary, attribution])

    head = [heading, escape_markdown(_summary_line(session), version=2)]
    table = _session_table(session, names)
    if table is not None:
        head += ["*Session*", table]

    sections = [_match_section(match, names) for match in session.matches]
    body, dropped = _trim_to_limit(head, sections, [attribution])

    _logger.debug(
        "Rendered CS2 results for %s: %d match(es), %d trimmed",
        session.event_date,
        len(session.matches),
        dropped,
    )
    return "\n\n".join(body)
