# ONGAbot

The one and only ON/GA Telegram bot, available on Docker Hub ([tingvarsson/telegram.ongabot](https://hub.docker.com/r/tingvarsson/telegram.ongabot/))

Built on [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)

## Setup

Copy `.env.example` to `.env` and fill in your Telegram bot token to avoid having to provide env var on the command line:

```bash
cp .env.example .env
# edit .env and set API_TOKEN=your_token
```

### Local Python environment

Recommended Python 3.14.

```bash
make venv
source venv/bin/activate
make install
make run
```

### Docker

```bash
make docker-build
make docker-run
```

The image is also published on [Docker Hub](https://hub.docker.com/r/tingvarsson/telegram.ongabot/) and can be run directly:

```bash
docker run --rm --env API_TOKEN=your_token tingvarsson/telegram.ongabot:latest
```

## CS2 match results

When an event completes, ONGAbot looks up the CS2 games played that day and posts a
"CS2 results" message with the maps, scores and each member's scoreboard. `/cs2` shows
the same thing on demand.

Match data comes from the [Leetify public API](https://api-public-docs.cs-prod.leetify.com/).
Setting `LEETIFY_API_KEY` in `.env` is optional — the public API works without a key, but
anonymous requests face tighter rate limits. Get one at
[leetify.com/app/developer](https://leetify.com/app/developer).

### Setting it up for a chat

Each member runs `/linksteam` once, so the bot knows which Steam account is theirs:

```text
/linksteam 76561198034202275
/linksteam https://steamcommunity.com/profiles/76561198034202275
```

A vanity `steamcommunity.com/id/<name>` URL will not work — resolving it needs a Steam Web
API key, which this bot deliberately avoids. Open your profile and copy the numeric
`/profiles/` URL instead. `/unlinksteam` undoes it.

**Only one member per match needs an actual [Leetify](https://leetify.com/) account.**
Leetify's match-detail endpoint returns the full ten-player scoreboard whether or not those
players use Leetify, so one enrolled member is enough to reveal a whole lobby. Everyone else
only needs `/linksteam`.

A match is reported as an ONGA game when at least two linked members appear on its
scoreboard. Only Valve matchmaking counts — competitive and Premier. Matches are attributed
to an event by the server's local calendar date.

Set `CS2_MIN_MEMBERS=1` to lower that threshold. This is meant for a test deployment where
only one person has linked an account — at two, nothing can ever reach the threshold and the
feature looks broken. Leave it unset in a real chat: at 1 the bot reports every matchmaking
game any single member plays.

Per Leetify's [Developer Guidelines](https://leetify.com/blog/leetify-api-developer-guidelines/),
no Leetify data is stored: stats are fetched when a message is rendered and then discarded.
ONGAbot persists only its own derived facts — who was seen playing, and whether the results
have been posted.

## Code cleaners

For code formatting `black` is used, together with `flake8` and `pylint` for linting.

Run locally to format with

```bash
> make black
black .
All done! ✨ 🍰 ✨
13 files left unchanged.

```

Run locally to check code with

```bash
> make check
black . --diff --check
All done! ✨ 🍰 ✨
16 files would be left unchanged.
pylint ongabot

--------------------------------------------------------------------
Your code has been rated at 10.00/10 (previous run: 10.00/10, +0.00)

flake8 ongabot tests
mypy -p ongabot
Success: no issues found in 1 source file

```

Alternatively each checker individually with

```bash
> make black-check
black . --diff --check
All done! ✨ 🍰 ✨
13 files would be left unchanged.

> make pep8
flake8 ongabot tests

> make lint
pylint ongabot

--------------------------------------------------------------------
Your code has been rated at 10.00/10 (previous run: 10.00/10, +0.00)

> make mypy
mypy -p ongabot
Success: no issues found in 1 source file

```

## Releasing

Releases are created with `bump-my-version`. The `release` target runs all checks and tests before bumping, then opens a PR for the version commit:

```bash
make release PART=patch   # 0.2.0 → 0.2.1
make release PART=minor   # 0.2.0 → 0.3.0
make release PART=major   # 0.2.0 → 1.0.0
```

This will:

1. Run `make check` and `make test` (aborts if either fails)
2. Update the version in `ongabot/_version.py` and commit
3. Push the commit to a `release/vX.Y.Z` branch and open a PR

After the PR is merged, CI automatically creates the `vX.Y.Z` git tag and the Docker workflow publishes the versioned image and updates `latest` on Docker Hub.

## Tests

Tests are located under `tests`. Run tests locally with

```bash
> make test
pytest -v
==================================================== test session starts ====================================================
platform linux -- Python 3.9.2, pytest-6.2.2, py-1.10.0, pluggy-0.13.1 -- /home/silly/git/tingvarsson/telegram.ongabot/venv/bin/python3
cachedir: .pytest_cache
rootdir: /home/silly/git/tingvarsson/telegram.ongabot
collected 1 item

tests/test_neweventcommand.py::NewEventCommandTest::test_getUpcomingWednesdayDate PASSED                              [100%]

===================================================== 1 passed in 0.13s =====================================================

```
