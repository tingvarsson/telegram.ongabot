"""Assemble a night's CS2 session from Leetify data.

This is the domain layer: it decides which matches belong to an event and who counts as
having played, and holds no HTTP or Telegram knowledge. cs2.leetify does the I/O,
cs2.format renders the result.

The attribution rule is deliberately loose in one direction and strict in the other. A match
is *discovered* through any linked member who has a Leetify account (the "scout"), but a
match is only *kept* when enough linked members appear on its scoreboard (see min_members) -
that scoreboard lists everyone in the lobby, Leetify account or not. So a group where only
one person uses Leetify still gets full results, which is the point.
"""

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Dict, List, Mapping, Optional, Protocol, Sequence, Set, Tuple

from telegram import User

from cs2.leetify import MatchDetail, MatchSummary, PlayerStats
from utils import log

if TYPE_CHECKING:  # pragma: no cover - import cycle: chat -> event -> ... -> cs2
    from chat import Chat
    from userdata import UserData

_logger = logging.getLogger(__name__)

# Valve matchmaking only: "matchmaking_competitive" is classic 5v5, "matchmaking" is Premier.
# FACEIT, wingman, casual and scrims are deliberately excluded - a 2v2 wingman game is not
# an ONGA night.
QUALIFYING_SOURCES = frozenset({"matchmaking_competitive", "matchmaking"})

# Two linked members in the same lobby already makes it a shared game. The rendered message
# always states how many took part, so a reader can judge a thin night for themselves.
DEFAULT_MIN_MEMBERS = 2


def min_members() -> int:
    """Linked members needed in one match before it counts as an ONGA game.

    CS2_MIN_MEMBERS overrides the default. Set it to 1 in a test deployment where only one
    person has linked an account - otherwise nothing can ever reach the threshold and the
    feature looks broken. Leave it unset in a real chat: at 1 the bot reports every
    matchmaking game any single member plays, which is a much noisier feature.
    """
    raw = os.getenv("CS2_MIN_MEMBERS")
    if raw is None:
        return DEFAULT_MIN_MEMBERS
    try:
        value = int(raw)
    except ValueError:
        _logger.warning("Ignoring non-numeric CS2_MIN_MEMBERS=%r; using %d", raw, DEFAULT_MIN_MEMBERS)
        return DEFAULT_MIN_MEMBERS
    if value < 1:
        _logger.warning("Ignoring CS2_MIN_MEMBERS=%d below 1; using %d", value, DEFAULT_MIN_MEMBERS)
        return DEFAULT_MIN_MEMBERS
    return value


class MatchSource(Protocol):
    """The slice of cs2.leetify.LeetifyClient this module needs, so it can be substituted."""

    async def get_match_history(self, steam64_id: str) -> Optional[List[MatchSummary]]:
        """Return the player's recent matches, or None if unavailable."""

    async def get_match(self, game_id: str) -> Optional[MatchDetail]:
        """Return the full scoreboard for a match, or None if unavailable."""


@dataclass(frozen=True)
class MemberLine:
    """One linked member's line on a match scoreboard."""

    user_id: int  # Telegram user id
    steam64_id: str
    name: str  # in-game name, as Leetify reports it
    total_kills: int
    total_deaths: int
    kd_ratio: float
    mvps: int
    team_number: int


@dataclass(frozen=True)
class Cs2Match:
    """One match that enough linked members played together to count as an ONGA game."""

    id: str  # Leetify game UUID, used for the View-on-Leetify link
    map_name: str
    finished_at: Optional[datetime]  # local time, None when the timestamp was unparseable
    score: Tuple[int, int]  # (members' side, opponents') when the members share a team
    members: Tuple[MemberLine, ...]

    @property
    def won(self) -> bool:
        """True when the members' side finished ahead."""
        return self.score[0] > self.score[1]


@dataclass(frozen=True)
class Cs2Session:
    """Every qualifying match played on one event's date."""

    event_date: date
    matches: List[Cs2Match]

    @property
    def played_user_ids(self) -> Set[int]:
        """Linked members seen in at least one qualifying match - ONGAbot's own derived fact."""
        return {member.user_id for match in self.matches for member in match.members}


def chat_members(chat: "Chat") -> Dict[int, User]:
    """Map user id to User for everyone who has ever answered a poll in this chat.

    The same roster utils.points and utils.statistics work from - poll answers are the only
    record ONGAbot keeps of who is in a chat. Events are walked oldest-first so the most
    recent User object wins, since display names change.
    """
    members: Dict[int, User] = {}
    for event in sorted(chat.events.values(), key=lambda e: e.event_date):
        for user in event.poll_answers:
            members[user.id] = user
    return members


def steam_links(chat: "Chat", user_data: Mapping[int, "UserData"]) -> Dict[int, str]:
    """Map user id to Steam64 for the chat members who have linked an account.

    user_data is Application.user_data, a read-only mapping - read it with .get so looking a
    member up never creates a persisted empty entry for someone who never linked.
    """
    links = {}
    for user_id in chat_members(chat):
        data = user_data.get(user_id)
        steam64_id = getattr(data, "steam64_id", None)
        if steam64_id:
            links[user_id] = steam64_id
    return links


def local_date(finished_at: str) -> Optional[date]:
    """Convert a Leetify UTC timestamp to the calendar date it falls on in server local time.

    Leetify reports finished_at as "...Z"; events are dated in local time. Comparing the two
    without converting is silently wrong for evening games under CEST - a 22:30Z match is
    already the next morning locally.
    """
    parsed = _parse_finished_at(finished_at)
    return None if parsed is None else parsed.date()


def _parse_finished_at(finished_at: str) -> Optional[datetime]:
    """Parse a Leetify UTC timestamp into a local-time datetime, or None if malformed."""
    try:
        return datetime.fromisoformat(finished_at.replace("Z", "+00:00")).astimezone()
    except (AttributeError, ValueError):
        _logger.warning("Could not parse Leetify finished_at=%r", finished_at)
        return None


def _score_for(detail: MatchDetail, members: Sequence[MemberLine]) -> Tuple[int, int]:
    """Round score as (members' side, opponents').

    Members are normally all on one team. When they are split across both - which happens if
    two of them queued into opposite sides - there is no "our side", so the score is reported
    highest-first rather than inventing a perspective.
    """
    scores = detail.team_scores
    teams = {member.team_number for member in members}
    if len(teams) == 1:
        ours = teams.pop()
        own = scores.get(ours, 0)
        other = max((score for team, score in scores.items() if team != ours), default=0)
        return own, other

    ordered = sorted(scores.values(), reverse=True)
    return (ordered[0] if ordered else 0), (ordered[1] if len(ordered) > 1 else 0)


def _member_line(player: PlayerStats, user_id: int) -> MemberLine:
    return MemberLine(
        user_id=user_id,
        steam64_id=player.steam64_id,
        name=player.name,
        total_kills=player.total_kills,
        total_deaths=player.total_deaths,
        kd_ratio=player.kd_ratio,
        mvps=player.mvps,
        team_number=player.initial_team_number,
    )


async def _candidate_match_ids(
    client: MatchSource,
    event_date: date,
    steam64_ids: Sequence[str],
) -> Tuple[Optional[List[str]], int]:
    """Collect ids of qualifying matches on event_date, plus how many histories we could read.

    Returns (None, 0) only when nobody's history could be read at all - the caller treats
    that as "Leetify unreachable" rather than "nobody played". Order is preserved so the
    number of detail calls is stable and testable.
    """
    seen: Dict[str, None] = {}
    reachable = 0
    for steam64_id in steam64_ids:
        history = await client.get_match_history(steam64_id)
        if history is None:
            continue
        reachable += 1
        for summary in history:
            if summary.data_source not in QUALIFYING_SOURCES:
                continue
            if local_date(summary.finished_at) != event_date:
                continue
            seen.setdefault(summary.id, None)

    if reachable == 0:
        return None, 0
    return list(seen), reachable


@log.log
async def build_session(
    client: MatchSource,
    event_date: date,
    links: Mapping[int, str],
) -> Optional[Cs2Session]:
    """Build the session for event_date from the chat's Telegram-user-id -> Steam64 links.

    Returns None when Leetify could not be reached for a single linked member, so a sweep can
    retry instead of announcing that nobody played. Returns a session with no matches when
    Leetify answered but nothing qualifying was found.
    """
    if not links:
        _logger.debug("No linked members, nothing to look up for %s", event_date)
        return Cs2Session(event_date, [])

    user_by_steam64 = {steam64_id: user_id for user_id, steam64_id in links.items()}

    match_ids, reachable = await _candidate_match_ids(client, event_date, list(links.values()))
    if match_ids is None:
        _logger.warning("No Leetify history could be read for any of %d linked members", len(links))
        return None

    threshold = min_members()
    matches = []
    for match_id in match_ids:
        detail = await client.get_match(match_id)
        if detail is None:
            _logger.warning("Skipping match %s: details could not be fetched", match_id)
            continue

        members = tuple(
            _member_line(player, user_by_steam64[player.steam64_id])
            for player in detail.players
            if player.steam64_id in user_by_steam64
        )
        if len(members) < threshold:
            _logger.debug("Skipping match %s: %d linked member(s), need %d", match_id, len(members), threshold)
            continue

        matches.append(
            Cs2Match(
                id=detail.id,
                map_name=detail.map_name,
                finished_at=_parse_finished_at(detail.finished_at),
                score=_score_for(detail, members),
                members=members,
            )
        )

    # datetime.min keeps a match with an unparseable timestamp in the list rather than
    # crashing the sort; it simply sorts first.
    matches.sort(key=lambda match: match.finished_at or datetime.min.astimezone())

    _logger.info(
        "CS2 session for %s: %d qualifying match(es) from %d readable history/histories",
        event_date,
        len(matches),
        reachable,
    )
    return Cs2Session(event_date, matches)
