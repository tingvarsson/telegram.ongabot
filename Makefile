DOCKER:=docker
PYTHON:=python3
PIP:=pip3
PYLINT=pylint
PEP8:=flake8
BLACK:=black
PYTEST:=pytest
MYPY:=mypy

API_TOKEN=OVERRIDE_ME
DOCKER_IMAGE=tingvarsson/telegram.ongabot:latest
VENV_PATH=venv

export PYTHONPATH=$PYTHONPATH:./ongabot

.PHONY: venv install run lint pep8 mypy black black-check check clean docker-build docker-run

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

black:
	$(BLACK) .

black-check:
	$(BLACK) . --diff --check

test:
	$(PYTEST) -v

check: black-check lint pep8 mypy

clean:
	rm -rf $(VENV_PATH)
	find . -name '*.pyc' -exec rm -f {} \;
	find . -name '*.pyo' -exec rm -f {} \;

docker-build:
	$(DOCKER) build . -f Dockerfile -t $(DOCKER_IMAGE)

docker-run:
	$(DOCKER) run --rm --env API_TOKEN=$(API_TOKEN) -it $(DOCKER_IMAGE)
