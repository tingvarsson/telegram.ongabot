# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **CS2 match results.** After an event completes, ONGAbot looks up the CS2
  games actually played that day and posts a "CS2 results" message. Data comes
  from the [Leetify public API][leetify-api]. The message opens with the date
  and the night's record (`3 matches · 2W 1L · 1 OT`), then a session table
  combining each member's kills, deaths and K/D across every match they played,
  then one scoreboard per match showing **all ten players** split by side, your
  team first, with the map, score, outcome and the time the match ended.
  Players are not individually marked: Telegram does not allow bold inside a
  code block, and the Session table already lists exactly the chat's members. Both tables carry kills, assists, deaths, K/D, ADR and aces;
  everyone is named by their Steam in-game name. Per-match K/D and ADR are Leetify's own `kd_ratio`
  and `dpr`, printed untouched; the session row sums raw counts instead, and its
  ADR is total damage over total rounds rather than an average of per-match
  averages, which would misweigh a short match against a long one.
  Clutches won, HLTV Rating and Utility Rating are not shown because the API
  exposes none of them: there is no clutch count, no HLTV rating, and utility
  rating exists only as a career-wide profile figure. A long night is trimmed to fit Telegram's message limit,
  oldest matches first, and says how many it dropped.
  Round-by-round detail and match start times are deliberately absent: Leetify
  exposes neither, and the only route to them would be downloading and parsing
  each match's demo.
  Only **one** member per match needs a Leetify account: Leetify's match-detail
  endpoint returns the full ten-player scoreboard whether or not those players
  use Leetify, so a single enrolled "scout" reveals the whole lobby. Everyone
  else just runs `/linksteam` so the bot recognises their Steam64.
  Results arrive as a separate follow-up message rather than inside the Banger
  Points recap, because that recap fires at midnight, before Leetify has
  processed the night's demos. A sweep job checks every 20 minutes and posts
  once the night's match list stops growing, giving up after 14 hours.
  A match counts as an ONGA game when at least 2 linked members appear on its
  scoreboard. Only Valve matchmaking counts - competitive and Premier; FACEIT,
  wingman and casual are excluded. Matches are attributed to the event's
  calendar date in server local time, since Leetify reports UTC and an evening
  game under CEST would otherwise land on the wrong day.
- New `/linksteam <steam64|profile URL>` and `/unlinksteam` commands. Linking is
  per-user and opt-in, since it publishes your match stats to the chat. A raw
  17-digit Steam64 or a `steamcommunity.com/profiles/<id>` URL both work; a
  vanity `/id/<name>` URL cannot be resolved without a Steam Web API key and is
  rejected with an explanation.
- New `/cs2 [target_date=<date|weekday>]` command to show the results for an
  event on demand, defaulting to the most recent completed event.
- Optional `LEETIFY_API_KEY` environment variable. The public API works without
  one; a key just raises the rate limits.
- Optional `CS2_MIN_MEMBERS` environment variable (default 2) to lower the
  threshold, for a test deployment where only one person has linked an account.

### Fixed

- Table name columns no longer shift out of line for names containing emoji,
  CJK characters or combining marks. Cells were padded by `len()`, which counts
  code points rather than monospace columns: a five-character Chinese name is
  ten columns wide, a combining accent is zero, and an emoji is unpredictable.
  Names are now measured by grapheme cluster rather than code point, so a ZWJ
  family sequence and a flag each count as the single glyph they render as.
  Emoji are assumed to be three columns wide, matching how Telegram renders
  them; that assumption is a single constant, `EMOJI_WIDTH`. A name mixing emoji with text drops
  the emoji, which keeps that row exact; a name that is *only* emoji keeps them,
  since two columns is a better guess than losing the name. Invisible format
  characters - zero-width joiners and bidi overrides, the latter also a spoofing
  vector - are always removed, and a name left with nothing renderable falls
  back to a short Steam64 tag. This also affects `/statistics` and
  `/leaderboard`, which share the same name-cell helper.

Per Leetify's [Developer Guidelines][leetify-guidelines], no Leetify data is
stored. Stats are fetched at render time, shown under Leetify's own field names,
and discarded; every message carries the required attribution and a per-match
"View on Leetify" link. The only things persisted are ONGAbot's own derived
facts - which members were seen playing, and whether results have been posted.
A Leetify outage cannot affect anything else: every call returns `None` on
failure, so polls, status messages and the Banger Points recap are unaffected,
and the sweep simply retries.

[leetify-api]: https://api-public-docs.cs-prod.leetify.com/
[leetify-guidelines]: https://leetify.com/blog/leetify-api-developer-guidelines/

## [1.6.0] - 2026-08-31

### Fixed

- `/statistics` Played Streak (`PStk`) showed 0 for every user on data predating
  1.5.0. Both streak columns were read from the latest event's stored
  `user_streaks` / `user_played_streaks` maps, which are only written when a vote
  arrives. `user_streaks` has been maintained since 1.1.0, so `RStk` was
  unaffected, but `user_played_streaks` shipped in 1.5.0 and was therefore empty
  on every already-persisted event. Both streaks are now derived from the event
  history that `/statistics` already walks, so they are correct immediately for
  all existing data and no longer depend on when the feature was deployed.

### Added

- New `/leaderboard` command showing **Banger Points**, a single score per user
  that weights each vote by how much it actually mattered rather than just
  counting votes. A vote earns more when it was decisive: picking the winning
  slot pays a clutch bonus scaled by how close that slot was to quorum (5
  players), plus an extra "rescue" when it landed on quorum exactly. Picking
  more slots helps with diminishing returns, so all five is not worth five times
  one, and propping up a slot the chat usually ignores earns a rarity bonus.
  Answering "No-op" beats ghosting, and being first to the poll pays too.
  Two standings are shown: **Form**, the rolling last 20 events, and All-time.
- A Banger Points recap is now posted to the chat when an event completes,
  showing what the poll decided, who scored what and why, and the top 5 of the
  Form table. Because polls are never closed, a late vote can still change an
  event's points afterwards - the recap is a snapshot at completion time, and
  `/leaderboard` recomputes live.

## [1.5.0] - 2026-08-31

### Fixed

- `make mypy` now type-checks all 34 modules instead of only the entry point.
  With `mypy_path = ongabot`, `mypy -p ongabot` resolved the package name to the
  `ongabot/ongabot.py` module and reported "no issues found in 1 source file",
  so type errors anywhere in the codebase passed CI unnoticed. The five errors
  this uncovered (across three files) are fixed; none affected runtime behavior.

### Changed

- Bumped `python-telegram-bot` from 22.7 to 22.8. Development tooling (black,
  mypy, pylint, pytest) and GitHub Actions were updated alongside it, with no
  user-facing effect.
- `/statistics` now shows first names only in the User Statistics table (a last
  initial is added when two users share a first name), making the table two
  columns narrower.
- `/statistics` `Avg` column is now the average number of slots picked per event
  the user could actually play, instead of per response. Answering "No-op" no
  longer drags the average down.
- `/statistics` "Average number of Bangers per event" now counts only the users
  who picked at least one slot, instead of everyone who answered the poll.
- `/statistics` slot popularity rows now merge near-identical times, so a start
  time that drifts between events (e.g. 20.30 and 20.40) is reported as one
  `20.30-20.40` row instead of two half-count rows.
- `/statistics` streak column is relabelled Response Streak (`RStk`), making it
  explicit that it counts events answered at all - "No-op" and "Maybe Baby </3"
  included - rather than events actually played.
- The ★ next to a voter in the poll status message now shows their played
  streak instead of their response streak, so the star means showing up.

### Added

- `/statistics` User Statistics gains a Played Streak column (`PStk`): the
  number of consecutive most-recent events in which the user picked an actual
  time slot. Sortable like every other column. A user who answers every poll
  with "No-op" now has a long Response Streak but a Played Streak of 0.

- `/statistics` Chat Statistics now includes "Average number of Bangers per
  slot" - all slot picks spread over every slot offered, i.e. how many players a
  single time slot typically draws.

## [1.4.0] - 2026-08-30

### Added

- `/statistics` shows all-time participation statistics in two sections: a
  Chat Statistics table (total/answered events with a % of total, average
  number of Bangers per event with a % of known chat users, and per-slot
  popularity, all in one aligned table with no header row) and a sortable
  User Statistics table with one row per user (response count and rate,
  current streak, "played" count and rate for actual slot picks, total
  slots picked, Maybe Baby/No-op counts, and a "didn't bother answer"
  count). Tap the buttons below the user table to re-sort it by any column.

## [1.3.1] - 2026-08-30

### Fixed

- Docker release builds now build from the actual checked-out ref instead of a
  remote git context tied to the triggering commit. Without an explicit `context: .`,
  `docker/build-push-action` silently ignored the `ref` passed to reusable workflow
  `_docker-build.yml`, so the nightly `latest` refresh rebuilt from `master`'s current
  tip instead of the pinned release tag — clobbering the clean release image with
  whatever `+dev` state `master` was in.

## [1.3.0] - 2026-07-09

### Added

- `/changelog [n]` shows the n most recent changelog entries (default 1)
- On development builds, `/changelog` shows the `[Unreleased]` section
- `/help` marks development builds with `(development build)` after the version
- `BotData.last_known_version` persists the last-seen release across restarts

### Changed

- Startup version announcement is skipped on development builds and only fires on
  clean release upgrades
- Deployments predating version tracking are migrated to a `1.2.0` starting point so
  the next release announces its delta
- Development builds carry a `+dev` version suffix (e.g. `1.2.0+dev`)

## [1.2.0] - 2026-05-24

### Fixed

- Events stuck at `0001-01-01` (sentinel date) from the initial broken v1.1.0 migration are
  now retroactively re-keyed to their real event dates on next load, by re-parsing the poll
  question text. Events whose questions cannot be parsed remain at their sentinel date unchanged.

## [1.1.0] - 2026-05-24

### Added

- User participation streak shown in bot responses (#290)
- Bot commands, description, and short description registered at startup via `set_my_*` API (#292)

### Fixed

- Migration of old polls no longer discards events due to date collisions on `0001-01-01`.
  The real event date is now recovered from the poll question text (`When: YYYY-MM-DD HH:MM`).
  For the rare case where parsing fails, duplicate events receive unique surrogate keys so
  all poll statistics are preserved.

### Changed

- Docker images now include OCI metadata labels: `version`, `revision`, `created`, `source`, `title`
  - Release images: `version` is the clean semver (e.g. `1.0.2`)
  - Edge/PR images: `version` includes the short commit SHA (e.g. `1.0.2-abc1234`)
- Removed redundant `nightly` Docker tag; `edge` is the single rolling non-release tag
- Event storage refactored to date-keyed `Chat.events` dict with `force=True` support (#293)

### Fixed

- Surgical `TelegramError` handling in poll/unpin callbacks; startup guard prevents job scheduling before bot is ready (#288)

## [1.0.2] - 2026-05-09

### CI

- Nightly Docker builds produce `edge` (latest commit) and versioned release tags (#285)

## [1.0.1] - 2026-05-09

No user-facing changes (version bump only).

## [1.0.0] - 2026-05-09

### Added

- Authorization system restricting bot commands to authorized users (#272)
- Flexible event creation with configurable day, time, and number of slots (#277)
- Custom `ContextTypes` and persistent event jobs that survive bot restarts (#129)
- Automatic scheduling of recurring event polls (#48)
- `Event` class with status message tracking in the group chat (#114)
- First responder's name displayed in event status message (#123)
- Static type checking with mypy (#42)

### Changed

- Updated runtime to Python 3.14 (#275)
- Updated to python-telegram-bot 22.7 (#273)
- Docker base image switched from `python:3.9-alpine` to `python:3.14-slim` (#253)

### Fixed

- Guard against `None` event in poll handler callbacks (#280)
- `@log` and `@log.method` decorators are now async-aware (#278)
- Correct ordering of answers displayed in status message (#258)
- Status message correctly updated when poll closes (#257)
- Failed poll message unpinning caught and handled gracefully (#122)
- Poll answer handling differentiates new/changed answers and ignores retractions (#41)
- "Maybe" answer no longer incorrectly processed (#128)

### CI

- Coverage enforcement with configurable minimum threshold and pip caching (#281)
- `bump-my-version` integrated for version management; Docker image tag semantics fixed (#282)

## [0.1.0] - 2021-03-15

Initial release — basic Telegram bot for recurring event polls in group chats.

[Unreleased]: https://github.com/tingvarsson/telegram.ongabot/compare/v1.6.0...HEAD
[1.6.0]: https://github.com/tingvarsson/telegram.ongabot/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/tingvarsson/telegram.ongabot/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/tingvarsson/telegram.ongabot/compare/v1.3.1...v1.4.0
[1.3.1]: https://github.com/tingvarsson/telegram.ongabot/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/tingvarsson/telegram.ongabot/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/tingvarsson/telegram.ongabot/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/tingvarsson/telegram.ongabot/compare/v1.0.2...v1.1.0
[1.0.2]: https://github.com/tingvarsson/telegram.ongabot/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/tingvarsson/telegram.ongabot/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/tingvarsson/telegram.ongabot/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/tingvarsson/telegram.ongabot/releases/tag/v0.1.0
