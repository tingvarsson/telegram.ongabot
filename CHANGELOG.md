# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/tingvarsson/telegram.ongabot/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/tingvarsson/telegram.ongabot/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/tingvarsson/telegram.ongabot/compare/v1.0.2...v1.1.0
[1.0.2]: https://github.com/tingvarsson/telegram.ongabot/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/tingvarsson/telegram.ongabot/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/tingvarsson/telegram.ongabot/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/tingvarsson/telegram.ongabot/releases/tag/v0.1.0
