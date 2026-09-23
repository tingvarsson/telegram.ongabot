"""Per-chat topic scoring for the daily YouTube Short.

Topics are open-ended - there is no fixed enum. A topic is just a lowercased word or tag
pulled from a video's title/tags (extract_topics), tracked per chat as a score in
Chat.topic_scores. Everything here is pure and has no I/O or Telegram knowledge; the
scheduling glue in ongabot.py and the reaction handler are the only callers.
"""

import re
from typing import Dict, Mapping, Optional, Sequence, Tuple

import random as _random

# Seeded so a brand new chat has an opinion from day one, matching this bot's existing
# CS2/gaming community focus, instead of picking uniformly at random until reactions
# accumulate.
SEED_TOPICS: Dict[str, float] = {"counter-strike": 3.0, "linux": 3.0}

NEUTRAL_SCORE = 1.0
# A floor above zero, not at it, so a topic's selection weight never hits zero and nothing
# can be permanently killed by one bad reaction.
MIN_SCORE = 0.1
MAX_SCORE = 10.0
# How much one added/removed reaction moves a topic's score; see reactions.py.
REACTION_STEP = 0.5
# Nightly pull toward NEUTRAL_SCORE, applied once by decay_topic_scores. Keeps a viral video
# from dominating selection forever and a single bad reaction from suppressing a topic forever.
DAILY_DECAY = 0.98
# Fraction of picks that ignore scores entirely and sample uniformly, so a newly registered
# topic (or one that hasn't drawn a reaction yet) still gets tried occasionally.
EXPLORATION_RATE = 0.15
# Upper bound on how many topics one chat tracks, so per-chat state doesn't grow unboundedly
# as new topics are discovered from every posted video's title/tags.
MAX_TRACKED_TOPICS = 50
MAX_TOPICS_PER_VIDEO = 5

_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "with",
        "is",
        "are",
        "this",
        "that",
        "shorts",
        "short",
        "video",
        "official",
        "new",
        "ft",
        "vs",
        "by",
        "its",
        "it's",
        "i",
        "you",
        "your",
        "my",
        "me",
        "we",
        "us",
        "our",
    }
)
_TOKEN_RE = re.compile(r"[a-z0-9']+")


def seed_topic_scores() -> Dict[str, float]:
    """A fresh per-chat topic_scores dict, seeded for a cold start."""
    return dict(SEED_TOPICS)


def extract_topics(title: str, tags: Sequence[str]) -> Tuple[str, ...]:
    """Pull candidate topics from a video's title and tags.

    Tags are taken near-verbatim (uploader-curated, already good signal) and come first;
    the title is tokenized, lowercased, and filtered against a small stopword list. Numbers
    and tokens under 3 characters are dropped as too generic to be a useful topic. Capped at
    MAX_TOPICS_PER_VIDEO so one video can't flood a chat's tracked-topic vocabulary.
    """
    seen: Dict[str, None] = {}
    for tag in tags:
        normalized = tag.strip().lower()
        if normalized:
            seen.setdefault(normalized, None)

    for token in _TOKEN_RE.findall((title or "").lower()):
        if len(token) < 3 or token in _STOPWORDS or token.isdigit():
            continue
        seen.setdefault(token, None)

    return tuple(list(seen)[:MAX_TOPICS_PER_VIDEO])


def choose_topic(scores: Mapping[str, float], rng: Optional[_random.Random] = None) -> str:
    """Pick one topic to search for, weighted by score with a flat exploration slice.

    Most picks are weighted-random proportional to score, so a chat's favourite topics come
    up more often without ever being a certainty. EXPLORATION_RATE of picks instead sample
    uniformly across every tracked topic, so a topic with little or no signal yet still gets
    tried - this is what keeps the bot from fixating on whatever scored highest first.
    """
    if not scores:
        raise ValueError("no topics to choose from")

    topics = list(scores.keys())
    roll = rng.random() if rng is not None else _random.random()
    if roll < EXPLORATION_RATE:
        return rng.choice(topics) if rng is not None else _random.choice(topics)

    weights = [max(scores[topic], MIN_SCORE) for topic in topics]
    if rng is not None:
        return rng.choices(topics, weights=weights, k=1)[0]
    return _random.choices(topics, weights=weights, k=1)[0]


def apply_reaction(scores: Dict[str, float], topics: Sequence[str], delta: float) -> None:
    """Adjust each of a video's topics by delta, clamped to [MIN_SCORE, MAX_SCORE]."""
    for topic in topics:
        current = scores.get(topic, NEUTRAL_SCORE)
        scores[topic] = min(MAX_SCORE, max(MIN_SCORE, current + delta))


def register_topics(scores: Dict[str, float], topics: Sequence[str]) -> None:
    """Track a posted video's topics at NEUTRAL_SCORE if they aren't tracked yet.

    Called after every post so a video's topics are selectable by choose_topic even before
    any reaction lands on them.
    """
    for topic in topics:
        scores.setdefault(topic, NEUTRAL_SCORE)


def _prune(scores: Dict[str, float]) -> None:
    """Cap scores at MAX_TRACKED_TOPICS, dropping the entries with the least signal first.

    Seed topics are always kept so a chat never loses its cold-start baseline; among the
    rest, the ones closest to NEUTRAL_SCORE (i.e. never reinforced) go first.
    """
    if len(scores) <= MAX_TRACKED_TOPICS:
        return

    protected = set(SEED_TOPICS) & scores.keys()
    candidates = sorted(
        (topic for topic in scores if topic not in protected),
        key=lambda topic: abs(scores[topic] - NEUTRAL_SCORE),
        reverse=True,
    )
    keep_count = max(MAX_TRACKED_TOPICS - len(protected), 0)
    keep = protected | set(candidates[:keep_count])
    for topic in list(scores):
        if topic not in keep:
            del scores[topic]


def decay_topic_scores(scores: Dict[str, float]) -> None:
    """Pull every score a little toward neutral, then prune. Run once daily, per chat."""
    for topic, score in list(scores.items()):
        scores[topic] = NEUTRAL_SCORE + (score - NEUTRAL_SCORE) * DAILY_DECAY
    _prune(scores)
