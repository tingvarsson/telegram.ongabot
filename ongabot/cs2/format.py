"""Render a CS2 session into the MarkdownV2 message ONGAbot posts.

Layout follows utils.points.format_event_recap: a bold heading, then fenced code blocks so
the columns line up in Telegram's monospace font. The message reads top-down as the night
did - what happened overall, how each member did across it, then match by match.

Two rules from Leetify's Developer Guidelines shape this module, and neither is optional:

* every message carries the ATTRIBUTION line and a View-on-Leetify link per match;
* per-match stats are shown exactly as Leetify reports them - kd_ratio is printed, never
  recomputed from kills and deaths, even though both are right there.

The one derived value is the session table's combined K/D, which Leetify does not supply per
session. Its inputs (total_kills, total_deaths) are raw Valve counts rather than Leetify
metrics, and it is the number people actually want out of a night. Session ADR is likewise
summed damage over summed rounds rather than an average of per-match averages, even though
raw damage itself is no longer a column - see _session_row_values.
"""

import logging
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from telegram.helpers import escape_markdown

from cs2.session import Cs2Match, Cs2Session, PlayerLine
from utils.statistics import fit_name

_logger = logging.getLogger(__name__)

MATCH_URL = "https://leetify.com/app/match-details/{id}"
ATTRIBUTION = "Data Provided by Leetify"

# Shown while the sweep is still running, so a reader knows the night is not over and more
# matches will be added to this same message.
LIVE_NOTE = "updating live - more matches may follow"

# Telegram rejects a message over 4096 characters outright, so a long night is trimmed
# rather than lost. The margin absorbs the "not shown" note appended after trimming.
MAX_MESSAGE_CHARS = 4096
TRIM_MARGIN_CHARS = 200

# CS2 tables get their own, narrower name column rather than utils.statistics.NAME_WIDTH,
# which /statistics and /leaderboard must keep at 10 - phone-width pressure here is worse
# since this module already carries six or seven stat columns per row.
CS2_NAME_WIDTH = 8

# Members are not marked on the board. Telegram forbids nesting bold inside a pre entity
# ("bold ... can contain and can be part of any other entities, except pre and code"), so
# there is no way to emphasise a row, and a punctuation marker just adds noise to every line.
# The Session table lists exactly the members, which is where to look for who is in the chat.
#
# K/A/D width differs by table: a single match rarely breaks two digits, but a session sums
# across the whole night and can. K/D, ADR and the session's match count are sized dynamically
# per table render instead of a fixed width - most nights need only the default, and only a
# table that actually has a row needing more (a double-digit K/D ratio, a triple-digit ADR,
# ten matches in a night) pays for the extra column. See _widen.
MATCH_KAD_WIDTH = 2
SESSION_KAD_WIDTH = 3
KD_DEFAULT_WIDTH = 4
ADR_DEFAULT_WIDTH = 3
ACES_WIDTH = 2  # "5K" - a night's multi-kill rounds are never more than two digits
MATCHES_DEFAULT_WIDTH = 1  # widened for a night of ten or more matches, see _widen
TEAM_DIVIDER = "--"


def _columns(*pairs: Tuple[str, int]) -> str:
    """Join right-aligned cells with a single space, as every table row does."""
    return " ".join(value.rjust(width) for value, width in pairs)


def _widen(values: Iterable[str], default: int) -> int:
    """default, or default + 1 when some value in this table's own rows needs the room.

    Only ever widens by one column: a K/D ratio or ADR that needs two extra digits over the
    default is an edge case rare enough not to design a table around.
    """
    longest = max((len(value) for value in values), default=0)
    return default if longest <= default else default + 1


def _name_cell(name: str, fallback: str = "?") -> str:
    """Pad/truncate a name to CS2_NAME_WIDTH monospace columns.

    Delegates to utils.statistics.fit_name, which measures display columns rather than code
    points - in-game names are full of emoji and CJK, and len() would shift the whole row.
    Escaping is applied to the whole code block rather than per cell, so this returns raw
    text; see _code_block.
    """
    return fit_name(name, CS2_NAME_WIDTH, fallback)


def _code_block(lines: Iterable[str]) -> str:
    """Wrap table lines in a MarkdownV2 fenced code block."""
    body = "\n".join(lines)
    return "```\n" + escape_markdown(body, version=2, entity_type="pre") + "\n```"


def _kd(kills: int, deaths: int) -> str:
    """Combined K/D over a session, or "-" when a member has not died yet."""
    return f"{kills / deaths:.2f}" if deaths else "-"


def _record_text(session: Cs2Session) -> str:
    """Win/loss/draw tally with each outcome's own overtime count.

    e.g. "2W (1 OT) - 3L (2 OT)". A zero-count outcome is dropped entirely, and the OT
    parenthetical is dropped for any outcome that had none - tracked per outcome rather than
    as one combined total, since "how many of our wins went to OT" and "how many losses did"
    are different questions a reader might ask.
    """
    tally: Dict[str, int] = {"W": 0, "L": 0, "D": 0}
    overtime_tally: Dict[str, int] = {"W": 0, "L": 0, "D": 0}
    for match in session.matches:
        tally[match.outcome] += 1
        if match.overtime:
            overtime_tally[match.outcome] += 1

    clauses = []
    for key in ("W", "L", "D"):
        if not tally[key]:
            continue
        clause = f"{tally[key]}{key}"
        if overtime_tally[key]:
            # A space before OT, so "1OT" doesn't read as "10" at a glance.
            clause += f" ({overtime_tally[key]} OT)"
        clauses.append(clause)
    return " - ".join(clauses)


def _stat_columns(kad_width: int, kd_width: int, adr_width: int) -> Tuple[Tuple[str, int], ...]:
    """The shared K/A/D/K-D/ADR/5K column spec, widths chosen for the calling table."""
    return (
        ("K", kad_width),
        ("A", kad_width),
        ("D", kad_width),
        ("K/D", kd_width),
        ("ADR", adr_width),
        ("5K", ACES_WIDTH),
    )


def _session_row_values(session: Cs2Session) -> Optional[List[Dict[str, str]]]:
    """Each linked member's night, combined across every match they appear in.

    Kept as raw values (not yet column-formatted) so the caller can measure the K/D and ADR
    strings across every row before deciding those columns' widths.
    """
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

    rows = []
    for user_id, row in sorted(totals.items(), key=lambda item: item[1]["k"], reverse=True):
        adr = row["damage"] / row["rounds"] if row["rounds"] else 0.0
        rows.append(
            {
                "name": names[user_id],
                "fallback": str(user_id),
                "m": f"{int(row['m'])}",
                "k": f"{int(row['k'])}",
                "a": f"{int(row['a'])}",
                "d": f"{int(row['d'])}",
                "kd": _kd(int(row["k"]), int(row["d"])),
                "adr": f"{adr:.0f}",
                "5k": f"{int(row['aces'])}",
            }
        )
    return rows


def _session_table(session: Cs2Session) -> Optional[str]:
    """The session-wide members' table: matches played plus combined stats."""
    rows = _session_row_values(session)
    if rows is None:
        return None

    kd_width = _widen((r["kd"] for r in rows), KD_DEFAULT_WIDTH)
    adr_width = _widen((r["adr"] for r in rows), ADR_DEFAULT_WIDTH)
    matches_width = _widen((r["m"] for r in rows), MATCHES_DEFAULT_WIDTH)
    columns = (("M", matches_width),) + _stat_columns(SESSION_KAD_WIDTH, kd_width, adr_width)

    header = "Name".ljust(CS2_NAME_WIDTH) + " " + _columns(*columns)
    lines = [header]
    for row in rows:
        lines.append(
            _name_cell(row["name"], fallback=row["fallback"])
            + " "
            + _columns(
                (row["m"], matches_width),
                (row["k"], SESSION_KAD_WIDTH),
                (row["a"], SESSION_KAD_WIDTH),
                (row["d"], SESSION_KAD_WIDTH),
                (row["kd"], kd_width),
                (row["adr"], adr_width),
                (row["5k"], ACES_WIDTH),
            )
        )
    return _code_block(lines)


def _session_block(session: Cs2Session) -> Optional[str]:
    """The "*Session*" heading, its win/loss record on the same line, and the members' table."""
    table = _session_table(session)
    if table is None:
        return None
    record = _record_text(session)
    heading = f"*Session* {escape_markdown(record, version=2)}" if record else "*Session*"
    return f"{heading}\n{table}"


def _match_row_values(player: PlayerLine) -> Dict[str, str]:
    """One player's stats as raw strings, not yet column-formatted."""
    return {
        "name": player.name,
        # An all-emoji name can sanitize to nothing, so fall back to the tail of the Steam64 -
        # short, aligned, and still tells two such players apart.
        "fallback": f"#{player.steam64_id[-4:]}",
        "k": f"{player.total_kills:d}",
        "a": f"{player.total_assists:d}",
        "d": f"{player.total_deaths:d}",
        "kd": f"{player.kd_ratio:.2f}",
        "adr": f"{player.adr:.0f}",
        "5k": f"{player.multi5k:d}",
    }


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


def _match_section(match: Cs2Match) -> str:
    """Heading, full ten-player scoreboard split by side, and the Leetify link - one section.

    Returned as a single already-joined string (heading, table and link glued with plain
    newlines) rather than a list, so the message-level join between *sections* never also
    ends up inside one: see format_session and _trim_to_limit.
    """
    ours = [player for player in match.players if player.team_number == match.our_team]
    theirs = [player for player in match.players if player.team_number != match.our_team]
    ordered = _sorted_side(ours) + _sorted_side(theirs)
    values = [_match_row_values(player) for player in ordered]

    kd_width = _widen((v["kd"] for v in values), KD_DEFAULT_WIDTH)
    adr_width = _widen((v["adr"] for v in values), ADR_DEFAULT_WIDTH)
    columns = _stat_columns(MATCH_KAD_WIDTH, kd_width, adr_width)

    header = "Name".ljust(CS2_NAME_WIDTH) + " " + _columns(*columns)
    lines = [header]
    for index, value in enumerate(values):
        if index == len(ours) and theirs:
            lines.append(TEAM_DIVIDER)
        lines.append(
            _name_cell(value["name"], fallback=value["fallback"])
            + " "
            + _columns(
                (value["k"], MATCH_KAD_WIDTH),
                (value["a"], MATCH_KAD_WIDTH),
                (value["d"], MATCH_KAD_WIDTH),
                (value["kd"], kd_width),
                (value["adr"], adr_width),
                (value["5k"], ACES_WIDTH),
            )
        )

    table = _code_block(lines)
    link_url = escape_markdown(MATCH_URL.format(id=match.id), version=2, entity_type="text_link")
    return f"{_match_heading(match)}\n{table}\n[View on Leetify]({link_url})"


def _trim_to_limit(head: List[str], sections: List[str], tail: List[str]) -> Tuple[List[str], int]:
    """Drop whole match sections, oldest first, until the message fits.

    Trimming by measurement rather than a fixed match cap, because in-game names vary in
    length and a fixed cap would be either wasteful or occasionally still too long.
    """
    kept = list(sections)
    dropped = 0
    while kept:
        body = head + kept + tail
        if len("\n\n".join(body)) <= MAX_MESSAGE_CHARS - TRIM_MARGIN_CHARS:
            break
        kept.pop(0)  # sections are chronological, so the oldest match goes first
        dropped += 1

    body = head + kept
    if dropped:
        note = escape_markdown(f"… and {dropped} earlier match{'es' if dropped != 1 else ''} not shown.", version=2)
        body.append(f"_{note}_")
        _logger.info("Trimmed %d match section(s) to fit Telegram's message limit", dropped)
    return body + tail, dropped


def format_session(session: Cs2Session, live: bool = False) -> str:
    """Format a session into the MarkdownV2 body of the CS2 results message.

    Everyone is labelled by their in-game name, members included: a CS2 scoreboard is a Steam
    scoreboard, and the marker on a row is what says who is in the chat. /statistics and
    /leaderboard keep Telegram names, since most of their users have no linked Steam account.

    live marks the message as still being updated by the sweep. The note joins the head of the
    message, so trimming accounts for it like everything else.
    """
    heading = f"*__CS2 results · {escape_markdown(str(session.event_date), version=2)}__*"
    attribution = f"_{escape_markdown(ATTRIBUTION, version=2)}_"

    if not session.matches:
        summary = escape_markdown(f"No ONGA matches found for {session.event_date}.", version=2)
        return "\n\n".join([heading, summary, attribution])

    head = [heading]
    if live:
        head.append(f"_{escape_markdown(LIVE_NOTE, version=2)}_")
    session_block = _session_block(session)
    if session_block is not None:
        head.append(session_block)

    sections = [_match_section(match) for match in session.matches]
    body, dropped = _trim_to_limit(head, sections, [attribution])

    _logger.debug(
        "Rendered CS2 results for %s: %d match(es), %d trimmed",
        session.event_date,
        len(session.matches),
        dropped,
    )
    return "\n\n".join(body)
