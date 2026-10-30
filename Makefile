# Build and test maps.sustenaut.eu. CI runs `make venv node` then
# `make functional` (pubkit.json's ci block). The build needs tippecanoe.

PYTHON ?= python3
VENV := .venv

.PHONY: download build node venv functional lock sync-check clean

download: venv
	bin/maps download

build: venv node
	bin/maps build

node: node_modules/.package-lock.json

node_modules/.package-lock.json: package.json package-lock.json
	npm ci

venv: $(VENV)/.done

$(VENV)/.done: tests/requirements.lock
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --quiet --require-hashes -r tests/requirements.lock
	touch $@

# The Gherkin suite, run against bin/maps, with its coverage in
# coverage/coverage.xml for SonarQube Cloud (.coveragerc).
functional: venv node
	rm -rf coverage && mkdir coverage
	cd tests && COVERAGE_RCFILE=$(CURDIR)/.coveragerc COVERAGE_FILE=$(CURDIR)/coverage/.coverage \
	  MAPS_BIN_DIR=$(CURDIR)/bin ../$(VENV)/bin/coverage run -m pytest -n auto
	COVERAGE_RCFILE=.coveragerc COVERAGE_FILE=coverage/.coverage $(VENV)/bin/coverage combine -q
	COVERAGE_RCFILE=.coveragerc COVERAGE_FILE=coverage/.coverage $(VENV)/bin/coverage xml -q

lock: venv
	$(VENV)/bin/pubkit lock

sync-check: venv
	$(VENV)/bin/pubkit sync --check

clean:
	rm -rf _site $(VENV)
