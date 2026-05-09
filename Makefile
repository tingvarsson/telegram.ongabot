DOCKER:=docker
PYTHON:=python3
PIP:=pip3
PYLINT=pylint
PEP8:=flake8
BLACK:=black
PYTEST:=pytest
MYPY:=mypy

-include .env
DOCKER_IMAGE=tingvarsson/telegram.ongabot:latest
VENV_PATH=venv

export PYTHONPATH=$PYTHONPATH:./ongabot

.PHONY: venv install run lint pep8 mypy black-check check black test clean docker-build docker-run release

.env:
	@echo "Error: .env not found. Copy .env.example and fill in your values: cp .env.example .env"
	@exit 1

venv:
	$(PYTHON) -m venv $(VENV_PATH)
	echo "To activate venv: source venv/bin/activate"

install:
	$(PIP) install -r requirements.txt
	$(PIP) install -r requirements-dev.txt

run: .env
	set -a && . ./.env && set +a && $(PYTHON) ongabot/ongabot.py

lint:
	$(PYLINT) ongabot

pep8:
	$(PEP8) ongabot tests

mypy:
	$(MYPY) -p ongabot

black-check:
	$(BLACK) . --diff --check

check: black-check lint pep8 mypy

black:
	$(BLACK) .

test:
	$(PYTEST) -v --cov=ongabot --cov-report=term-missing --cov-fail-under=46

clean:
	rm -rf $(VENV_PATH)
	find . -name '*.pyc' -exec rm -f {} \;
	find . -name '*.pyo' -exec rm -f {} \;

docker-build:
	$(DOCKER) build . -f Dockerfile -t $(DOCKER_IMAGE)

docker-run: .env
	touch ongabot.db
	$(DOCKER) run --rm --env-file .env -v $(CURDIR)/ongabot.db:/ongabot/ongabot.db -it $(DOCKER_IMAGE)

release: check test
	bump-my-version bump $(PART) && \
	NEW_VERSION=$$(grep -oE '[0-9]+\.[0-9]+\.[0-9]+' ongabot/_version.py) && \
	BRANCH="release/v$$NEW_VERSION" && \
	git push origin HEAD:refs/heads/$$BRANCH && \
	gh pr create --title "chore: bump version to $$NEW_VERSION" --body "Release v$$NEW_VERSION" --base master --head $$BRANCH && \
	echo "" && \
	echo "After the PR is merged, push the release tag: git push origin v$$NEW_VERSION"
