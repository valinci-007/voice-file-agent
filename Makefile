VENV := .venv
PY := $(VENV)/bin/python

.PHONY: setup run test integration lint fmt selftest clean

setup:            ## create venv and install in editable mode with dev tools
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --quiet -e ".[dev]"

run:              ## start the agent (voice mode)
	./run.sh

test:             ## fast hermetic unit tests
	$(VENV)/bin/pytest

integration:      ## local-only tests (Whisper closed loop; needs macOS)
	$(VENV)/bin/pytest -m integration

lint:             ## ruff lint
	$(VENV)/bin/ruff check src tests

fmt:              ## ruff format
	$(VENV)/bin/ruff format src tests

selftest:         ## offline diagnostics (Spotlight, apps, open, STT)
	$(VENV)/bin/voice-file-agent --selftest

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache src/*.egg-info dist build
