VENV := .venv/bin

# The scope of the archaeology gate: shipped code and tooling. tests/ is out by
# decision — a regression test names the bug it pins, in whatever tense the bug
# demands.
SOURCES := $(shell git ls-files 'triviajudge/*.py' 'scripts/*.py')

# The length gate governs tests too, at its own limit. The citation gate reads
# whatever can carry a citation: code and markdown alike.
ALL_PY := $(shell git ls-files '*.py')
DOCS := $(shell git ls-files '*.md')

.PHONY: lint test check trivia

lint:
	$(VENV)/ruff check triviajudge tests scripts
	$(VENV)/black --check triviajudge tests scripts
	$(VENV)/xenon --max-absolute B --max-average A --max-modules A triviajudge
	$(VENV)/vulture
	$(VENV)/mypy
	$(VENV)/triviajudge-archaeology $(SOURCES)
	$(VENV)/python scripts/gates/check_file_length.py $(ALL_PY)
	$(VENV)/python scripts/gates/check_doc_refs.py $(ALL_PY) $(DOCS)
	$(VENV)/python scripts/gates/check_changelog.py CHANGELOG.md
	git log -1 --format=%B | $(VENV)/python scripts/gates/check_commit_msg.py -
	$(VENV)/python scripts/gates/check_control_catalog.py
	$(VENV)/python scripts/gates/check_settings_docs.py
	$(VENV)/python scripts/gates/check_gates_wired.py

# The coverage floor is per file and lives in the gate below, not in
# --cov-fail-under. Second recipe line, so a failing suite reports first.
test:
	$(VENV)/pytest -q --cov=triviajudge --cov-branch --cov-report=term-missing --cov-report=json:.coverage.json
	$(VENV)/python scripts/gates/check_coverage_floor.py

check: lint test

# Asks a model whether the prose HEAD added narrates history instead of stating
# what holds now. Needs a logged-in `claude` CLI and the network, so it stays
# out of `check`, which is offline by contract; pre-commit runs it per commit.
trivia:
	$(VENV)/triviajudge-md --head
	$(VENV)/triviajudge-comments --head
