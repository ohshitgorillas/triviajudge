VENV := .venv/bin

# The scope of the archaeology gate: shipped code and tooling. tests/ is out by
# decision — a regression test names the bug it pins, in whatever tense the bug
# demands.
SOURCES := $(shell git ls-files 'triviajudge/*.py' 'scripts/*.py')

# The length gate governs tests too, at its own limit. The citation gate reads
# whatever can carry a citation: code and markdown alike.
ALL_PY := $(shell git ls-files '*.py')
DOCS := $(shell git ls-files '*.md')

# The two assertion gates read tests and nothing else: shape is a property of the
# suite, not of what it covers.
TESTS := $(shell git ls-files 'tests/*.py')

.PHONY: lint duplication test check mutate trivia

lint:
	$(VENV)/ruff check triviajudge tests scripts
	$(VENV)/black --check triviajudge tests scripts
	$(VENV)/xenon --max-absolute B --max-average A --max-modules A triviajudge
	$(VENV)/vulture
	$(VENV)/mypy
	$(VENV)/lint-imports
	$(VENV)/triviajudge-archaeology $(SOURCES)
	$(VENV)/python scripts/gates/check_file_length.py $(ALL_PY)
	$(VENV)/python scripts/gates/check_nesting.py $(ALL_PY)
	$(VENV)/python scripts/gates/check_no_barrels.py $(SOURCES)
	$(VENV)/python scripts/gates/check_test_assertions.py $(TESTS)
	$(VENV)/python scripts/gates/check_no_copy_assertions.py $(TESTS)
	$(VENV)/python scripts/gates/check_doc_refs.py $(ALL_PY) $(DOCS)
	$(VENV)/python scripts/gates/check_changelog.py CHANGELOG.md
	git log -1 --format=%B | $(VENV)/python scripts/gates/check_commit_msg.py -
	$(VENV)/python scripts/gates/check_control_catalog.py
	$(VENV)/python scripts/gates/check_settings_docs.py
	$(VENV)/python scripts/gates/check_release.py
	$(VENV)/python scripts/gates/check_gates_wired.py

# jscpd is an npx tool, and `lint` is the venv-only half that stays runnable
# with no node_modules installed, so the duplication gate has its own target.
# Its whole configuration — paths, format, threshold — is in .jscpd.json, so the
# recipe is a bare invocation. `npm install` puts jscpd in node_modules, which is
# what keeps this offline.
duplication:
	npx jscpd

# The coverage floor is per file and lives in the gate below, not in
# --cov-fail-under. Second recipe line, so a failing suite reports first.
# The junit report carries the suite's wall time; the third line holds it to the
# last green run's (scripts/gates/check_suite_time.py).
test:
	$(VENV)/pytest -q --cov=triviajudge --cov-branch --cov-report=term-missing --cov-report=json:.coverage.json --junitxml=.pytest-junit.xml
	$(VENV)/python scripts/gates/check_coverage_floor.py
	$(VENV)/python scripts/gates/check_suite_time.py

check: lint duplication test

# Mutation testing, by hand and never in `check`: it breaks the code one edit at
# a time and reports how many of those breakages the suite noticed, which takes
# far longer than a commit path allows. MUTATE is an fnmatch pattern over mutant
# names, so the trailing `.*` is load-bearing — a bare module name matches no
# mutant and mutmut asserts rather than running:
#
#     make mutate                              # everything under triviajudge/
#     make mutate MUTATE='triviajudge.core.*'  # one module
#
# `mutmut run` exits non-zero when mutants survive, which is the normal outcome
# and not a reason to skip the report, hence the leading `-`. Scope and pytest
# arguments live in pyproject.toml under [tool.mutmut]; the working copies go in
# the gitignored mutants/ directory, rebuilt from scratch every run because
# mutmut copies a file only when its target is absent.
mutate:
	rm -rf mutants
	-$(VENV)/mutmut run $(MUTATE)
	$(VENV)/mutmut results

# Asks a model whether the prose HEAD added narrates history instead of stating
# what holds now. Needs a logged-in `claude` CLI and the network, so it stays
# out of `check`, which is offline by contract; pre-commit runs it per commit.
trivia:
	$(VENV)/triviajudge-md --head
	$(VENV)/triviajudge-comments --head
