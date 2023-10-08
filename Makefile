DOCKER:=docker
PYTHON:=python3
PIP:=pip3
PYLINT=pylint
PEP8:=flake8
BLACK:=black
PYTEST:=pytest
MYPY:=mypy

API_TOKEN=OVERRIDE_ME
DOCKER_IMAGE=tingvarsson/telegram.togabot:latest
VENV_PATH=venv

export PYTHONPATH=$PYTHONPATH:./togabot

.PHONY: venv install run lint pep8 mypy black-check check black test clean docker-build docker-run

venv:
	$(PYTHON) -m venv $(VENV_PATH)
	echo "To activate venv: source venv/bin/activate"

install:
	$(PIP) install -r requirements.txt
	$(PIP) install -r requirements-dev.txt

run:
	cd togabot && API_TOKEN=$(API_TOKEN) $(PYTHON) togabot.py

lint:
	$(PYLINT) togabot

pep8:
	$(PEP8) togabot tests

mypy:
	$(MYPY) -p togabot

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

docker-run:
	$(DOCKER) run --rm --env API_TOKEN=$(API_TOKEN) -it $(DOCKER_IMAGE)
