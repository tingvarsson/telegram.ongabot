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

.PHONY: venv install run lint pep8 mypy black-check check black test clean docker-build docker-run

venv:
	$(PYTHON) -m venv $(VENV_PATH)
	echo "To activate venv: source venv/bin/activate"

install:
	$(PIP) install -r requirements.txt
	$(PIP) install -r requirements-dev.txt

run:
	cd ongabot && API_TOKEN=$(API_TOKEN) $(PYTHON) ongabot.py

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
	$(PYTEST) -v

clean:
	rm -rf $(VENV_PATH)
	find . -name '*.pyc' -exec rm -f {} \;
	find . -name '*.pyo' -exec rm -f {} \;

docker-build:
	$(DOCKER) build . -f Dockerfile -t $(DOCKER_IMAGE)

.env:
	@echo "Error: .env not found. Copy .env.example and fill in your values: cp .env.example .env"
	@exit 1

docker-run: .env
	$(DOCKER) run --rm --env-file .env -it $(DOCKER_IMAGE)
