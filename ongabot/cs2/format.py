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
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from telegram.helpers import escape_markdown

from cs2.session import Cs2Match, Cs2Session, PlayerLine
from utils.statistics import NAME_WIDTH, fit_name

_logger = logging.getLogger(__name__)

MATCH_URL = "https://leetify.com/app/match-details/{id}"
ATTRIBUTION = "Data Provided by Leetify"

# Telegram rejects a message over 4096 characters outright, so a long night is trimmed
# rather than lost. The margin absorbs the "not shown" note appended after trimming.
MAX_MESSAGE_CHARS = 4096
TRIM_MARGIN_CHARS = 200

# Members are not marked on the board. Telegram forbids nesting bold inside a pre entity
# ("bold ... can contain and can be part of any other entities, except pre and code"), so
# there is no way to emphasise a row, and a punctuation marker just adds noise to every line.
# The Session table lists exactly the members, which is where to look for who is in the chat.
# Column widths. The board runs to 39 columns and the session table to 41; Telegram code
# blocks scroll rather than wrap on desktop, and this is the set of stats the chat asked for.
KILLS_WIDTH = 3
ASSISTS_WIDTH = 3
DEATHS_WIDTH = 3
KD_WIDTH = 5
DAMAGE_WIDTH = 5  # a long overtime match tops out around 5000; a session total needs five
ADR_WIDTH = 4
ACES_WIDTH = 3
MATCHES_WIDTH = 3
TEAM_DIVIDER = "--"

# Leetify supplies kd_ratio and dpr per match, and those are printed untouched. The session
# row combines raw counts instead - kills/deaths summed, and damage over rounds rather than
# an average of per-match averages, which would misweigh a short match against a long one.
STAT_COLUMNS = (
    ("K", KILLS_WIDTH),
    ("A", ASSISTS_WIDTH),
    ("D", DEATHS_WIDTH),
    ("K/D", KD_WIDTH),
    ("DMG", DAMAGE_WIDTH),
    ("ADR", ADR_WIDTH),
    ("ACE", ACES_WIDTH),
)


def _columns(*pairs: Tuple[str, int]) -> str:
    """Join right-aligned cells with a single space, as every table row does."""
    return " ".join(value.rjust(width) for value, width in pairs)


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


def _session_table(session: Cs2Session) -> Optional[str]:
    """Each linked member's night, combined across every match they appear in."""
    totals: Dict[int, Dict[str, float]] = {}
    names: Dict[int, str] = {}
    for match in session.matches:
        for member in match.members:
            row = totals.setdefault(
                member.user_id, {"m": 0, "k": 0, "a": 0, "d": 0, "aces": 0, "damage": 0, "rounds": 0}
            )
            row["m"] += 1
            row["k"] += member.total_kills
            row["a"] += member.total_assists
            row["d"] += member.total_deaths
            row["aces"] += member.multi5k
            row["damage"] += member.total_damage
            row["rounds"] += member.rounds_count
            # Matches are in chronological order, so the last one wins: names change.
            names[member.user_id] = member.name

    if not totals:
        return None

    header = "Name".ljust(NAME_WIDTH) + " " + _columns(("M", MATCHES_WIDTH), *STAT_COLUMNS)
    lines = [header]
    for user_id, row in sorted(totals.items(), key=lambda item: item[1]["k"], reverse=True):
        adr = row["damage"] / row["rounds"] if row["rounds"] else 0.0
        lines.append(
            _name_cell(names[user_id], fallback=str(user_id))
            + " "
            + _columns(
                (f"{int(row['m'])}", MATCHES_WIDTH),
                (f"{int(row['k'])}", KILLS_WIDTH),
                (f"{int(row['a'])}", ASSISTS_WIDTH),
                (f"{int(row['d'])}", DEATHS_WIDTH),
                (_kd(int(row["k"]), int(row["d"])), KD_WIDTH),
                (f"{int(row['damage'])}", DAMAGE_WIDTH),
                (f"{adr:.0f}", ADR_WIDTH),
                (f"{int(row['aces'])}", ACES_WIDTH),
            )
        )
    return _code_block(lines)


def _player_row(player: PlayerLine) -> str:
    """One scoreboard line, labelled with the in-game name Leetify reports.

    CS2 views name everyone by their Steam identity, members included.
    """
    # An all-emoji name can sanitize to nothing, so fall back to the tail of the Steam64 -
    # short, aligned, and still tells two such players apart.
    return (
        _name_cell(player.name, fallback=f"#{player.steam64_id[-4:]}")
        + " "
        + _columns(
            (f"{player.total_kills:d}", KILLS_WIDTH),
            (f"{player.total_assists:d}", ASSISTS_WIDTH),
            (f"{player.total_deaths:d}", DEATHS_WIDTH),
            (f"{player.kd_ratio:.2f}", KD_WIDTH),
            (f"{player.total_damage:d}", DAMAGE_WIDTH),
            (f"{player.adr:.0f}", ADR_WIDTH),
            (f"{player.multi5k:d}", ACES_WIDTH),
        )
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


def _match_section(match: Cs2Match) -> List[str]:
    """Heading, full ten-player scoreboard split by side, and the Leetify link."""
    header = "Name".ljust(NAME_WIDTH) + " " + _columns(*STAT_COLUMNS)
    ours = [player for player in match.players if player.team_number == match.our_team]
    theirs = [player for player in match.players if player.team_number != match.our_team]

    lines = [header]
    lines += [_player_row(player) for player in _sorted_side(ours)]
    if theirs:
        lines.append(TEAM_DIVIDER)
        lines += [_player_row(player) for player in _sorted_side(theirs)]

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


def format_session(session: Cs2Session) -> str:
    """Format a session into the MarkdownV2 body of the CS2 results message.

    Everyone is labelled by their in-game name, members included: a CS2 scoreboard is a Steam
    scoreboard, and the marker on a row is what says who is in the chat. /statistics and
    /leaderboard keep Telegram names, since most of their users have no linked Steam account.
    """
    heading = f"*__CS2 results · {escape_markdown(str(session.event_date), version=2)}__*"
    attribution = f"_{escape_markdown(ATTRIBUTION, version=2)}_"

    if not session.matches:
        summary = escape_markdown(f"No ONGA matches found for {session.event_date}.", version=2)
        return "\n\n".join([heading, summary, attribution])

    head = [heading, escape_markdown(_summary_line(session), version=2)]
    table = _session_table(session)
    if table is not None:
        head += ["*Session*", table]

    sections = [_match_section(match) for match in session.matches]
    body, dropped = _trim_to_limit(head, sections, [attribution])

    _logger.debug(
        "Rendered CS2 results for %s: %d match(es), %d trimmed",
        session.event_date,
        len(session.matches),
        dropped,
    )
    return "\n\n".join(body)
