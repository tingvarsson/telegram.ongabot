DOCKER:=docker
PYTHON:=python3
PIP:=pip3
PYLINT=pylint
PEP8:=flake8
BLACK:=black
PYTEST:=pytest
MYPY:=mypy

DOCKER_IMAGE=tingvarsson/telegram.ongabot:latest
VENV_PATH=venv
# Dev bot for run/stop/docker-run: a file name in .env.d/ (e.g. ongadev2). Empty picks one automatically.
BOT ?=
DEVBOT = $(PYTHON) scripts/devbot.py

export PYTHONPATH=$PYTHONPATH:./ongabot

.PHONY: venv install run stop status lint pep8 mypy black-check check black test snapshots clean docker-build docker-run release post-release

venv:
	$(PYTHON) -m venv $(VENV_PATH)
	echo "To activate venv: source venv/bin/activate"

install:
	$(PIP) install -r requirements.txt
	$(PIP) install -r requirements-dev.txt

run:
	$(DEVBOT) run $(if $(BOT),--bot $(BOT))

stop:
	$(DEVBOT) stop $(if $(BOT),--bot $(BOT))

status:
	$(DEVBOT) status

lint:
	$(PYLINT) ongabot

pep8:
	$(PEP8) ongabot tests

mypy:
	$(MYPY) ongabot

black-check:
	$(BLACK) . --diff --check

check: black-check lint pep8 mypy

black:
	$(BLACK) .

test:
	$(PYTEST) -v --cov=ongabot --cov-report=term-missing --cov-fail-under=93

# Rewrite tests/snapshots/ from the current renderers; review the diff before committing.
snapshots:
	UPDATE_SNAPSHOTS=1 $(PYTEST) -q tests/test_snapshots.py

clean:
	rm -rf $(VENV_PATH)
	find . -name '*.pyc' -exec rm -f {} \;
	find . -name '*.pyo' -exec rm -f {} \;

docker-build:
	$(DOCKER) build . -f Dockerfile -t $(DOCKER_IMAGE)

docker-run:
	touch ongabot.db
	ENV_FILE=$$($(DEVBOT) env-file $(if $(BOT),--bot $(BOT))) && \
	$(DOCKER) run --rm --env-file "$$ENV_FILE" -v $(CURDIR)/ongabot.db:/ongabot/ongabot.db -it $(DOCKER_IMAGE)

release: check test
	bump-my-version bump $(PART) && \
	NEW_VERSION=$$(python scripts/version.py --base) && \
	python scripts/update_changelog.py $$NEW_VERSION && \
	git add CHANGELOG.md && \
	git commit -m "docs: update CHANGELOG for v$$NEW_VERSION" && \
	BRANCH="release/v$$NEW_VERSION" && \
	git push origin HEAD:refs/heads/$$BRANCH && \
	gh pr create --title "chore: bump version to $$NEW_VERSION" --body "Release v$$NEW_VERSION" --base master --head $$BRANCH

post-release:
	@NEW_VERSION=$$(python scripts/version.py --base) && \
	sed -i -E "s/^__version__ = \"$$NEW_VERSION\"\$$/__version__ = \"$$NEW_VERSION+dev\"/" ongabot/_version.py && \
	echo "Set development version $$NEW_VERSION+dev in ongabot/_version.py"
