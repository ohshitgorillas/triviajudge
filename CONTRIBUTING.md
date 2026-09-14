# Contributing to Trivia Judge

## Bug reports

To report a bug, please give:

* the Trivia Judge version, and the Python version it runs under
* the gate and the mode (`--head`, `--stop`, a pre-commit run, the plugin hook)
* the line that was flagged, or the line that should have been and was not
* the `[tool.triviajudge]` table of the repository being judged

## Setup

```sh
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pre-commit install
```

`pre-commit install` wires both the pre-commit and the commit-msg stage, because
`.pre-commit-config.yaml` declares `default_install_hook_types`. Without that
install the commit-message gate never runs on a commit.

The package itself is the standard library alone. Everything in the `dev` extra
belongs to `make check`.

## Before you open a PR

`make check` must be green. `make lint` is the offline half — ruff, black,
xenon, vulture, mypy in strict mode, and the gates under `scripts/gates/`.
`make test` runs the suite and then the per-file coverage floor, which is 90%
for every file, not an average.

`make trivia` is separate and is not part of `check`: it asks a model whether
the prose `HEAD` added narrates history, so it needs the `claude` CLI and the
network. `check` is offline by contract.

## The changelog

Every user-visible change lands with a `CHANGELOG.md` entry under
`[Unreleased]`, in the same commit as the change. Write it for the person
hitting the problem, not for the person who fixed it.

The shape is one line, a bold lead first:

```
- **What it does now.** What went wrong before, and anything the reader has to know to recognize it.
```

`scripts/gates/check_changelog.py` enforces the mechanical half of that on
`[Unreleased]` — released sections are history and are never rewritten. It
refuses an entry over 75 words, an entry running to a second paragraph, an entry
not opening with a bold lead, second person (`you`, `your`), marketing register
(`simply`, `seamless`, `finally`, `quietly`, `significantly`, …), narration by
negation (`is unchanged`, `unaffected`, `untouched`, `nothing else changes`, …),
and a duplicate or out-of-order `###` heading. The order is Keep a Changelog's,
plus `Internal` for changes with no user-visible face.

Narration by negation is the one an author reaches for while trying to be
helpful. A changelog says what changed, and a reader already assumes anything it
does not mention stayed put, so the clause carries nothing. Where it is
load-bearing it is a scope boundary, and a scope boundary reads positively:
"only markdown the sweep collected is judged", not "the comment candidates are
untouched".

What the gate cannot check is tone. Three rules it will never catch:

- **No implementation archaeology.** Flag names, file paths, the order a gate
  does things in, the two things you had to work out to fix it — none of that
  helps someone reading a release note. It is in the commit.
- **State the change; do not sell it.** "the cache now works properly" is a
  verdict on your own work. "a passed line stays passed wherever it moves" is
  the change.
- **One entry per change, not one per commit.** Three commits fixing one bug
  are one entry.

## Commit messages

A commit message records the change and the reason for it. It may state what was
wrong and why the fix is shaped as it is, in whatever tense the bug demands.
What it may not carry is the road there: which attempt came first, what a
session or a reviewer did, what somebody worked out along the way, a dated
remark, a tally of a file's past.

`scripts/gates/check_commit_msg.py` runs at the commit-msg stage and refuses
those shapes in the subject and body. Git's `#` comment lines and the trailing
block of `Key: value` trailers are out of scope, which is where a session link
lives. A line that must stay takes `history-ok: <reason>`, reason required — the
same contract the comment gate offers.

## File length

A source file is capped at 500 lines, a test file at 800. Above 400 lines a
source file also enters a ratchet: it carries an entry in `ALLOWANCE` in
`scripts/gates/check_file_length.py` and may only ever get shorter. Growing past
the entry fails, and so does measuring under it — the gate makes you lower the
number to match, so headroom cannot be banked in one commit and spent in the
next. Nothing raises an allowance. A file that needs more room needs a split.
The ratchet does not reach under `tests/`, where one assertion per test inflates
line count without adding coupling.

## Citing the documentation

A comment that points at this repository's markdown cites the target's **heading
text**, which moves with the content it names:

```python
# the judged repository names its own file scope
# (README.md "The judged repository configures the gates")
```

`scripts/gates/check_doc_refs.py` fails a quoted citation that resolves to no
heading, or to more than one, and rejects a `round N` or `step N` citation
outright — those number a position in a narrative that nothing maintains. A
citation must sit on one line, since matching is per line; where a heading is
long, cite a unique prefix rather than wrapping. The escape hatch is
`doc-ref-exempt: <reason>` on the line or the one above it.

## The three cross-checks

Three gates hold tables in step that nothing else compares:

- `check_control_catalog.py` holds the four gate names together across
  `[project.scripts]`, the `.pre-commit-hooks.yaml` ids and `hooks/hooks.json`.
  `CATALOG` in that file is the single statement of what exists, and it says
  which gates a hook may run: `sweep` is a console script and must appear in no
  hook table, because judging the whole tree is an explicit user act.
- `check_settings_docs.py` pairs every `Settings` field in
  `triviajudge/config.py` with its line in the README's `[tool.triviajudge]`
  block, both ways. A documented key the dataclass has no field for is the worse
  drift of the two: `config.read` refuses an unknown key, so the README would be
  telling a reader to write a line that stops their commits.
- `check_gates_wired.py` holds `.pre-commit-config.yaml` in step with the
  Makefile. Makefile wiring is mandatory with no exemption — a gate that should
  not run is a gate that should be deleted. Absence from pre-commit takes a
  reason in `PRECOMMIT_EXEMPT`, and a reason naming no gate fails as stale.

A new gate is wired into both the `lint` target and `.pre-commit-config.yaml` in
the change that adds it, and holds to the standard it polices: mypy strict, the
ruff set in `pyproject.toml`, and black at 120 columns. `scripts/` is inside
mypy's and vulture's paths and outside `--cov=triviajudge`, so a gate carries no
coverage obligation.

## Licence

Contributions are under the MIT licence, the same as the project.
