# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- CS2 results now follow the night as it happens. The sweep starts at the
  event's start time instead of after midnight, posts as soon as Leetify has
  the first match, and edits that same message as later matches land. It is
  marked as updating live until no new match has appeared for 90 minutes.
- `/changelog` sends long output as several messages instead of failing on
  Telegram's 4096-character limit, as does the version announcement on upgrade.
  The 1.7.0 entry, which was over that limit, has been cut down to what it
  actually changed for users.

## [1.7.0] - 2026-08-31

### Added

- **CS2 match results.** ONGAbot looks up the CS2 games played on an event's
  date and posts a "CS2 results" message: the night's record
  (`3 matches · 2W 1L · 1 OT`), a session table combining each member's stats
  across every match they played, and a full ten-player scoreboard per match
  with map, score, outcome and end time. Data comes from the
  [Leetify public API][leetify-api]; nothing from Leetify is stored. Only Valve
  matchmaking counts (competitive and Premier), and a match is an ONGA game
  when at least 2 linked members appear on its scoreboard. Only one member per
  match needs an actual Leetify account - see the README for setup.
- `/linksteam <steam64|profile URL>` and `/unlinksteam`. Opt-in and per user,
  since linking publishes your match stats to the chat. A vanity `/id/<name>`
  URL is rejected: resolving it needs a Steam Web API key.
- `/cs2 [target_date=<date|weekday>]` shows an event's results on demand,
  defaulting to the most recent completed event.
- Optional `LEETIFY_API_KEY` (raises Leetify's rate limits) and
  `CS2_MIN_MEMBERS` (default 2) environment variables.

### Fixed

- Table name columns no longer shift out of line for names containing emoji,
  CJK characters or combining marks. Cells were padded by `len()`, which counts
  code points rather than monospace columns; names are now measured by grapheme
  cluster. Also affects `/statistics` and `/leaderboard`.

[leetify-api]: https://api-public-docs.cs-prod.leetify.com/

## [1.6.0] - 2026-08-31

### Fixed

- `/statistics` Played Streak (`PStk`) showed 0 for every user on data predating
  1.5.0: it was read from the latest event's stored `user_played_streaks` map,
  which only 1.5.0 onwards ever wrote. Both streaks are now derived from the
  event history, so they are correct for all existing data.

### Added

- New `/leaderboard` command showing **Banger Points**, a single score per user
  that weights each vote by how much it mattered rather than just counting
  votes. Picking the winning slot pays a clutch bonus, scaled by how close that
  slot was to quorum and topped up when the vote landed on quorum exactly.
  Picking more slots helps with diminishing returns, propping up an unpopular
  slot earns a rarity bonus, "No-op" beats ghosting, and answering first pays.
  Two standings are shown: **Form**, the rolling last 20 events, and All-time.
- A Banger Points recap is posted to the chat when an event completes, showing
  what the poll decided, who scored what and why, and the top 5 of the Form
  table. It is a snapshot at completion time - a late vote can still change an
  event's points afterwards, and `/leaderboard` recomputes live.

## [1.5.0] - 2026-08-31

### Fixed

- `make mypy` now type-checks all 34 modules instead of only the entry point:
  `mypy -p ongabot` resolved to the `ongabot/ongabot.py` module alone, so type
  errors anywhere else passed CI unnoticed. The five errors this uncovered are
  fixed; none affected runtime behavior.

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

[Unreleased]: https://github.com/tingvarsson/telegram.ongabot/compare/v1.7.0...HEAD
[1.7.0]: https://github.com/tingvarsson/telegram.ongabot/compare/v1.6.0...v1.7.0
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
