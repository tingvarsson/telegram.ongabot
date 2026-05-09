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
