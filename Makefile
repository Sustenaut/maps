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

# The Gherkin suite, run against bin/maps.
functional: venv node
	cd tests && MAPS_BIN_DIR=$(CURDIR)/bin ../$(VENV)/bin/pytest -n auto

lock: venv
	$(VENV)/bin/pubkit lock

sync-check: venv
	$(VENV)/bin/pubkit sync --check

clean:
	rm -rf _site $(VENV)
