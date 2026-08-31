"""Thin async client for the Leetify public CS API.

This module is I/O only - it knows how to talk to Leetify and how to parse the handful of
fields ONGAbot uses, and nothing about events or chats. See cs2.session for the domain logic.

Two endpoints carry the whole feature:

* ``/v3/profile/matches`` returns a player's ~100 most recent matches, but the ``stats``
  array holds only the queried player.
* ``/v2/matches/{id}`` returns the same match with ``stats`` for all ten players, whether or
  not they have a Leetify account.

That asymmetry is what makes partial enrolment workable: one member with a Leetify account
is enough to reveal a match, and the detail call then exposes every other ONGA member in
that lobby. See cs2.session.build_session.

API docs: https://api-public-docs.cs-prod.leetify.com/
Usage is subject to https://leetify.com/blog/leetify-api-developer-guidelines/ - in
particular, responses are rendered and discarded, never persisted.
"""

import functools
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import httpx

_logger = logging.getLogger(__name__)

BASE_URL = "https://api-public.cs-prod.leetify.com"

# Leetify answers in well under a second; a slow reply means something is wrong upstream and
# the sweep is better off retrying on its next pass than holding the job queue open.
TIMEOUT_SECONDS = 10.0
# One retry only. The caller is a repeating sweep job, so a transient blip is picked up on
# the next pass anyway - hammering a keyless public API buys nothing.
MAX_ATTEMPTS = 2


@dataclass(frozen=True)
class MatchSummary:
    """One entry of a player's match history - just enough to decide whether we want it."""

    id: str
    finished_at: str  # ISO-8601, UTC ("...Z"); converted to local time in cs2.session
    data_source: str  # e.g. "matchmaking_competitive", "matchmaking" (Premier), "faceit"
    map_name: str


@dataclass(frozen=True)
class PlayerStats:
    """One player's line on a match scoreboard, under Leetify's own field names."""

    steam64_id: str
    name: str
    total_kills: int
    total_deaths: int
    kd_ratio: float
    mvps: int
    initial_team_number: int


@dataclass(frozen=True)
class MatchDetail:
    """A full match scoreboard: every player in the lobby, not only Leetify users."""

    id: str
    finished_at: str
    data_source: str
    map_name: str
    team_scores: Dict[int, int]  # team_number -> rounds won
    players: Tuple[PlayerStats, ...]


def _parse_match_summary(raw: Dict[str, Any]) -> MatchSummary:
    return MatchSummary(
        id=str(raw["id"]),
        finished_at=str(raw["finished_at"]),
        data_source=str(raw["data_source"]),
        map_name=str(raw.get("map_name") or ""),
    )


def _parse_player(raw: Dict[str, Any]) -> PlayerStats:
    return PlayerStats(
        steam64_id=str(raw["steam64_id"]),
        name=str(raw.get("name") or ""),
        total_kills=int(raw.get("total_kills") or 0),
        total_deaths=int(raw.get("total_deaths") or 0),
        kd_ratio=float(raw.get("kd_ratio") or 0.0),
        mvps=int(raw.get("mvps") or 0),
        initial_team_number=int(raw.get("initial_team_number") or 0),
    )


def _parse_match_detail(raw: Dict[str, Any]) -> MatchDetail:
    return MatchDetail(
        id=str(raw["id"]),
        finished_at=str(raw["finished_at"]),
        data_source=str(raw.get("data_source") or ""),
        map_name=str(raw.get("map_name") or ""),
        team_scores={int(t["team_number"]): int(t["score"]) for t in raw.get("team_scores") or []},
        players=tuple(_parse_player(p) for p in raw.get("stats") or []),
    )


class LeetifyClient:
    """Async Leetify public API client that never raises on failure.

    Every method returns None when the data could not be fetched or understood, so a Leetify
    outage degrades into "no CS2 message" rather than breaking the job or handler that called
    it. Callers cannot distinguish "no account" from "upstream down" per-call; cs2.session
    decides what an all-None sweep means.

    An api_key raises the rate limits the public API applies to anonymous callers; get one at
    leetify.com/app/developer and set LEETIFY_API_KEY.
    """

    def __init__(self, api_key: Optional[str] = None, base_url: str = BASE_URL) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        # Created on first use so constructing a client never opens a connection pool, and so
        # tests can substitute their own transport before anything is allocated.
        self._client: Optional[httpx.AsyncClient] = None

    def _http(self) -> httpx.AsyncClient:
        """Return the shared AsyncClient, creating it on first use."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=TIMEOUT_SECONDS)
        return self._client

    async def aclose(self) -> None:
        """Close the underlying connection pool."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(self, path: str, params: Optional[Dict[str, str]] = None) -> Optional[Any]:
        """GET a path and return decoded JSON, or None on any failure whatsoever."""
        url = f"{self._base_url}{path}"
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await self._http().get(url, params=params, headers=headers, timeout=TIMEOUT_SECONDS)
            except httpx.HTTPError as e:
                _logger.warning("Leetify request failed (attempt %d) for %s: %s", attempt, path, e)
                continue

            if response.status_code == 404:
                # The common, expected case: this player has no Leetify account.
                _logger.debug("Leetify has no data for %s (404)", path)
                return None
            if response.status_code >= 400:
                _logger.warning("Leetify returned HTTP %d (attempt %d) for %s", response.status_code, attempt, path)
                continue

            try:
                return response.json()
            except ValueError as e:
                _logger.warning("Leetify returned malformed JSON for %s: %s", path, e)
                return None

        return None

    async def get_match_history(self, steam64_id: str) -> Optional[List[MatchSummary]]:
        """Return the player's recent matches, or None if unavailable (no account, or an error)."""
        payload = await self._get("/v3/profile/matches", {"steam64_id": steam64_id})
        if not isinstance(payload, list):
            if payload is not None:
                _logger.warning("Leetify match history for %s was not a list", steam64_id)
            return None

        try:
            matches = [_parse_match_summary(raw) for raw in payload]
        except (KeyError, TypeError, ValueError) as e:
            _logger.warning("Could not parse Leetify match history for %s: %s", steam64_id, e)
            return None

        _logger.debug("Leetify returned %d matches for steam64_id=%s", len(matches), steam64_id)
        return matches

    async def get_match(self, game_id: str) -> Optional[MatchDetail]:
        """Return the full scoreboard for a match, or None if unavailable."""
        payload = await self._get(f"/v2/matches/{game_id}")
        if not isinstance(payload, dict):
            if payload is not None:
                _logger.warning("Leetify match detail for %s was not an object", game_id)
            return None

        try:
            match = _parse_match_detail(payload)
        except (KeyError, TypeError, ValueError) as e:
            _logger.warning("Could not parse Leetify match detail for %s: %s", game_id, e)
            return None

        _logger.debug("Leetify match %s on %s with %d players", match.id, match.map_name, len(match.players))
        return match


@functools.lru_cache(maxsize=1)
def get_client() -> LeetifyClient:
    """Return the process-wide LeetifyClient, so one connection pool is shared.

    Deliberately not stored on BotData: that object is pickled by PicklePersistence, and an
    httpx client is not picklable. LEETIFY_API_KEY is read once, on first use.
    """
    api_key = os.getenv("LEETIFY_API_KEY") or None
    _logger.info("Leetify client initialised (api_key=%s)", "set" if api_key else "unset")
    return LeetifyClient(api_key=api_key)
