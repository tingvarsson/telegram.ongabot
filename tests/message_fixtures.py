"""One small, fixed chat history that the message tests render.

tests/test_message_markup.py checks the markup of these renders and tests/test_snapshots.py
pins their text, so both see the same data. It is realistic enough to read like a real chat,
and it includes one hostile name (NASTY) so every renderer is exercised on untrusted input too.
Everything is deterministic: no clock, no randomness.
"""

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import List, Optional, Tuple
from unittest.mock import MagicMock

from telegram import User

from ongabot.chat import Chat
from ongabot.cs2.session import Cs2Match, Cs2Session, PlayerLine
from ongabot.cs2.steamnews import SteamNewsItem
from ongabot.event import Event
from ongabot.eventdata import EventData
from ongabot.utils.statistics import MAYBE_TEXT, NO_OP_TEXT

FIXTURES = Path(__file__).parent / "fixtures"

# Every character MarkdownV2 reserves, every one HTML needs escaped, a backslash, and text
# that is wider in UTF-16 than it looks.
NASTY = '_*[]()~`>#+-=|{}.!\\ <b>&amp; "q" \U0001f389'
SLOTS = ["18.30", "19.10", "19.50"]
FIRST_EVENT = date(2026, 9, 2)
CHAT_ID = 42

# Option indexes into SLOTS + [NO_OP_TEXT, MAYBE_TEXT].
_NO_OP = len(SLOTS)
_MAYBE = len(SLOTS) + 1

# One tuple of picks per user (in users() order) per weekly event; () is a retracted vote.
WEEKLY_PICKS: List[List[Tuple[int, ...]]] = [
    [(0, 1), (0,), (_NO_OP,), (0, 1, 2)],
    [(0, 1, 2), (_MAYBE,), (1,), (1, 2)],
    [(2,), (0, 2), (), (0, 1, 2)],
]


def users() -> List[User]:
    return [
        User(id=1, first_name="Tommy", is_bot=False),
        User(id=2, first_name="Anna", last_name="Svensson", is_bot=False),
        User(id=3, first_name="Émile", is_bot=False),
        User(id=4, first_name=NASTY, is_bot=False),
    ]


def event(event_date: date, members: List[User], picks: List[Tuple[int, ...]]) -> Event:
    """A completed event whose poll offers SLOTS plus the two joke options."""
    texts = SLOTS + [NO_OP_TEXT, MAYBE_TEXT]
    poll = MagicMock()
    poll.id = f"poll-{event_date}"
    poll.total_voter_count = sum(1 for pick in picks if pick)
    poll.options = [MagicMock(text=text, voter_count=sum(i in pick for pick in picks)) for i, text in enumerate(texts)]
    result = Event(chat_id=CHAT_ID, poll=poll, data=EventData(event_date, time(18, 30), len(SLOTS)))
    for user, pick in zip(members, picks):
        answer = MagicMock()
        answer.option_ids = pick
        result.poll_answers[user] = answer
    result.first_answer = members[0]
    result.user_played_streaks = {user.id: 3 for user in members}
    result.completed = True
    return result


def chat() -> Chat:
    """Three weekly events with every kind of answer: slots, No-op, Maybe Baby, retracted."""
    members = users()
    result = Chat(CHAT_ID)
    for week, picks in enumerate(WEEKLY_PICKS):
        weekly = event(FIRST_EVENT + timedelta(weeks=week), members, picks)
        result.events[weekly.event_date] = weekly
    return result


def latest_event(history: Chat) -> Event:
    return max(history.events.values(), key=lambda weekly: weekly.event_date)


def _player(index: int, user_id: Optional[int], name: str, team: int, kills: int, deaths: int) -> PlayerLine:
    rounds = 20
    adr = 60.0 + 3 * kills
    return PlayerLine(
        user_id=user_id,
        steam64_id=f"7656119800000{index:04d}",
        name=name,
        total_kills=kills,
        total_deaths=deaths,
        kd_ratio=round(kills / deaths, 2),
        mvps=kills // 7,
        team_number=team,
        total_assists=index + 2,
        adr=adr,
        multi5k=1 if kills > 25 else 0,
        total_damage=int(adr * rounds),
        rounds_count=rounds,
    )


def cs2_session() -> Cs2Session:
    """Two matches the chat played on FIRST_EVENT, one won and one lost."""
    ours = [
        _player(1, 1, "tommy", 2, 27, 14),
        _player(2, 2, "anna_sv", 2, 18, 16),
        _player(4, 4, NASTY, 2, 9, 19),
    ]
    theirs = [_player(10, None, "xX_s1lent_Xx", 3, 22, 17), _player(11, None, "foe", 3, 12, 20)]
    won = Cs2Match(
        id="2fae0fe6-a164-4c38-a2ee-c30d7b9dc57b",
        map_name="de_mirage",
        finished_at=datetime(2026, 9, 2, 20, 10),
        score=(13, 7),
        our_team=2,
        players=tuple(ours + theirs),
    )
    lost = Cs2Match(
        id="8c1d2a4e-0b7f-4c1e-9d3a-5e6f7a8b9c0d",
        map_name="de_ancient",
        finished_at=datetime(2026, 9, 2, 21, 2),
        score=(9, 13),
        our_team=2,
        players=tuple(ours[:2] + theirs),
    )
    return Cs2Session(FIRST_EVENT, [won, lost])


def steam_patch_notes() -> List[SteamNewsItem]:
    """The patch-note posts in the recorded Steam news fixture, newest first."""
    payload = json.loads((FIXTURES / "steam_news_cs2.json").read_text(encoding="utf-8"))
    return [
        SteamNewsItem(
            gid=str(raw["gid"]),
            title=raw["title"],
            url=raw["url"],
            contents=raw.get("contents") or "",
            date=int(raw["date"]),
            tags=tuple(raw.get("tags") or []),
        )
        for raw in payload["appnews"]["newsitems"]
    ]
