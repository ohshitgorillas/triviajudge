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
npm install
```

`pre-commit install` wires both the pre-commit and the commit-msg stage, because
`.pre-commit-config.yaml` declares `default_install_hook_types`. Without that
install the commit-message gate never runs on a commit.

The package itself is the standard library alone. Everything in the `dev` extra
belongs to `make check`, except `mutmut`, which `make mutate` runs by hand.
`npm install` puts one tool in `node_modules`: jscpd, the duplication gate that
`make duplication` runs. It is the only node dependency, and installing it is
what keeps that gate offline.

## Before you open a PR

`make check` must be green. `make lint` is the offline half — ruff check, ruff
format, xenon, vulture, mypy in strict mode, import-linter, and the gates under
`scripts/gates/`.
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

`triviajudge-changelog` enforces that on `[Unreleased]` — released sections are
history and are never rewritten. Its pattern screen holds the mechanical half: it
refuses an entry over 75 words, an entry running to a second paragraph, an entry
not opening with a bold lead, second person (`you`, `your`), marketing register
(`simply`, `seamless`, `finally`, `quietly`, `significantly`, …), narration by
negation (`is unchanged`, `unaffected`, `untouched`, `nothing else changes`, …),
and a duplicate or out-of-order `###` heading. The order is Keep a Changelog's,
plus `Internal` for changes with no user-visible face.

What the screen leaves goes to the judge, which reads an entry for the shape a
pattern cannot name: a flag name or a file path as the subject, the order a gate
runs its steps in, cause narration, mechanism where the reader needs the effect,
and what the code did in an earlier release. It runs per commit through the
`changelog-style` hook and over `HEAD` in `make trivia`, so it needs the `claude`
CLI and the network and stays out of `make check`.

Narration by negation is the one an author reaches for while trying to be
helpful. A changelog says what changed, and a reader already assumes anything it
does not mention stayed put, so the clause carries nothing. Where it is
load-bearing it is a scope boundary, and a scope boundary reads positively:
"only markdown the sweep collected is judged", not "the comment candidates are
untouched".

What no pattern reaches is tone, which is the judge's half. Three rules it
holds you to:

- **No implementation archaeology.** Flag names, file paths, the order a gate
  does things in, the two things you had to work out to fix it — none of that
  helps someone reading a release note. It is in the commit.
- **State the change; do not sell it.** "the cache now works properly" is a
  verdict on your own work. "a passed line stays passed wherever it moves" is
  the change.
- **One entry per change, not one per commit.** Three commits fixing one bug
  are one entry.

## Changelog shape

`scripts/gates/check_changelog.py` is the offline half of the rule above, and it
makes no model call, so it runs in `make lint` where the judge cannot. Its scope
is the whole `[Unreleased]` section rather than the lines a commit adds: a bullet
reshaped by a commit that adds no line to it, a heading a rebase duplicates, a
kind order a merge scrambles — none of those reach the judge's screen, and each
otherwise ships.

Four rules: a bullet runs to at most 75 words, opens with a bold lead clause,
and addresses no reader; and one `###` heading per kind, in Keep a Changelog's
order plus `Internal`. Register and tone stay with the judge, because a wordlist
is a poor proxy for either and the rule would then be stated twice. Released
sections are history and are never read.

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

## Shape

Three gates hold the tree's shape where line count says nothing.

`scripts/gates/check_nesting.py` caps a function at four nested blocks. xenon and
ruff `C901` count branches, so a branch-cheap function that indents five deep
passes both and still asks the reader to hold five conditions at once. A site
that must stand carries its reason in `EXEMPT`, keyed `path::qualified.name`.

`scripts/gates/check_no_barrels.py` refuses the two shapes that shorten a file
without simplifying the tree: a module of imports and nothing else, and a method
whose whole body forwards its own arguments somewhere else. Both read as a
finished split to anything counting lines, and neither moved a caller.

`lint-imports` reads the layer contract in `pyproject.toml`. The package is one
layer per module — `sweep` over the two judges, the judges over `archaeology`,
then `core`, then `config` — and the two judges share a layer, so an import
between them fails. The one edge that runs upward is `config` reaching `core`
for the work tree, deferred to call time and named in `ignore_imports`.

## Tests

`docs/testing.md` is the binding testing policy: what a test may assert, what a
fake may be, what leaves the suite and how. The sections below describe the
mechanics of the gates that enforce its mechanical half; the rule each one
serves is cited there by number.

## One assertion per test

`scripts/gates/check_test_assertions.py` holds a `test_` function to exactly one
assertion — an `assert` statement or a `pytest.raises` context, counting one per
operand of a conjunction at the root. A test that pins six things reports the
first one that breaks and hides the rest, and its name can only describe one of
them. Where two facts are one behavior, compare them as a tuple:
`assert (finished.returncode, finished.stderr) == (0, "")`.

The same gate refuses four more shapes: an assertion inside a loop or under
`all()`/`any()`, which is an unparametrized case sweep; an `assert` in a
module-level helper, since a helper returns evidence and a fixture that must
refuse raises; an assertion whose whole condition is `x is not None` or
`len(x) > 0`, which pins presence where a value was owed; and a
`skip`/`skipif`/`xfail` decorator. A reach for a single-underscore attribute on
anything but `self` is reported too. A site that must stand carries its reason in
`EXEMPT`, keyed `<path>::<test name>`, and only the existence and skip categories
may be exempted.

## No copy in assertions

`scripts/gates/check_no_copy_assertions.py` refuses a literal of two or more
words asserted, or matched by `pytest.raises(match=...)`, unless the test itself
put those words there. A sentence the gate wraps around a value is prose the
author rewords at will: a test pinning it goes red on a rewording and green on a
broken behavior.

So a refusal is matched on what the test seeded — the timeout it asked for, the
stderr its fake wrote, the key it named — rather than on the sentence carrying
it: `match="no credit"` where the fake wrote `no credit`, not
`match="claude exited 1: no credit"`. A literal counts as seeded when it appears
in the test file outside an assertion, is handed to a plain function on the
assert line, sits inside a longer seeded string, is composed of seeded pieces, or
matches an f-string a fake wrote.

## Real clocks in tests

`scripts/gates/check_test_clocks.py` refuses two shapes anywhere under `tests/`,
with no carve-out directory. A `time.sleep` or `asyncio.sleep` is one, unless its
argument is the literal `0`, which is a scheduler yield; the argument's spelling
does not matter otherwise, since a paced fake names its wait with a constant as
readily as with a literal. A `timeout` or `*_timeout` keyword or mapping key
given a numeric literal under 0.5 is the other: at seconds such a knob is a
ceiling a test never reaches, and at a fraction of a second it is a deadline the
code waits out.

Every clock a test here reads belongs to a seam the suite owns — a fake the
fixtures build, a monkeypatched call — so a real wait is a test pacing itself
against the machine it runs on. A per-test duration threshold catches neither
shape: a ten millisecond poll over seventy call sites lifts no test over any
threshold, and a deadline waited out inside a spawned gate reads as CPU rather
than as idle.

## Exemptions carry reasons

`scripts/gates/check_noqa_reasons.py` requires an em dash and a clause after the
codes of every `noqa` and every `type: ignore` comment, as in
`# noqa: CODE — why the check is wrong here`. A `type: ignore` puts that clause
behind a second `#`, which is the only tail mypy accepts after its codes.
Ruff's `PGH` rules already hold each to naming its codes,
which stops one suppression from swallowing whatever the next edit breaks, and a
code is not a reason — it names the check, which the reader has from the checker
anyway. What the line cannot otherwise recover is the argument: that the argv is
the module's own constants, that the field is a dataclass keyword mypy cannot see
through. Absent it, the only safe reading is that somebody wanted a gate quiet.

The sweep reads comment tokens, so a suppression spelled inside a string is data,
which is what lets the gate's own tests feed it one. A colon after the codes
reads as more codes, hence the em dash.

## Hook timeouts

`scripts/gates/check_hook_timeouts.py` holds each `timeout` in
`hooks/hooks.json` at or above the largest timeout constant the module that hook
runs can reach: the constants that module states, and `triviajudge/core.py`'s,
which every mode calls into through the diff it reads. Where the hook's timeout
is smaller, the constant is unreachable — the harness kills the gate before its
own bound can fire, so the gate's message naming the command that never answered
never runs, and a wedged `git` reads as a flaky hook.

The comparison is over constants, not call sites. A call stating `timeout=None`
waits forever and no hook timeout covers it; that decision belongs to the call
site, and "Calls that wait" is where it is held.

## The standard library alone

`scripts/gates/check_stdlib_only.py` walks the AST of every file under
`triviajudge/` and refuses an import naming anything outside
`sys.stdlib_module_names` and the package itself. The empty `dependencies` list
in `pyproject.toml` is what lets a consumer install this package with no
resolver, and nothing else holds the code to it: import-linter reads the layers
inside the package, and a third-party import installs cleanly on the machine
that adds it.

Imports inside a function body and inside a `TYPE_CHECKING` block count the
same as one at module scope. The `dev` extra is where a third-party tool
belongs; `scripts/` runs on that extra and is outside this gate's scope.

## Calls that wait

`scripts/gates/check_call_timeouts.py` requires a `timeout=` keyword on every
`subprocess.run` and `urlopen` in `triviajudge/` and `scripts/gates/`. Both wait
forever by default, and a hook captures its output, so a wedged `git` or a
server that answers nothing hangs a commit with no line saying which call is
waiting.

The value belongs to the caller — a local `git` needs seconds, a model call
needs minutes — and `timeout=None` is the way to say a call may wait forever,
which puts that decision at the call site. The match is on the call's spelling,
so a call reached through an alias is outside what the gate sees.

## Suite time

`scripts/gates/check_suite_time.py` reads the junit report `make test` writes and
compares the suite's wall time with the last green run's, kept in the gitignored
`.suite-time.json`. A run within five seconds of the baseline passes and becomes
the baseline. A run past that needs `--accept`; a run ten seconds or more over is
refused either way, and the way past it is a faster suite. A red report is not
judged and not recorded, because an aborted run looks fast. A fresh checkout has
no baseline and seeds one from its first run.

## Duplication

`make duplication` runs jscpd over `triviajudge/`, `scripts/` and `tests/`. A
clone of 50 tokens or more counts, and the tree is held under 1% duplicated
tokens. The whole configuration — paths, format, threshold — is in
`.jscpd.json`, so both the Makefile recipe and the pre-commit hook are a bare
invocation, and the gate reads the entire source set rather than the staged
filenames: a clone has two ends and either one can move.

It sits in its own target rather than in `lint`, which is the venv-only half and
stays runnable with no `node_modules` installed. `check` runs both.

## Mutation testing

`make mutate` runs by hand and is in neither `check` nor pre-commit. Scope,
invocation and how to read a survivor are in `docs/testing.md`
("Mutation testing").

## Cutting a release

`scripts/gates/check_release.py` holds five statements of the version together:
`version` in `pyproject.toml`, `version` in `.claude-plugin/plugin.json`,
`metadata.version` in `.claude-plugin/marketplace.json`, the newest released
`## [x.y.z]` heading in `CHANGELOG.md`, and the `vx.y.z` tags in git.

- `version` equals the newest released heading. `[Unreleased]` is not a release
  and never satisfies it.
- Each plugin manifest states that same version. `claude plugin validate
  --strict` in CI reads their shape, not their agreement with the package, so a
  release that bumps four of the five ships a plugin whose version is a
  different release's.
- A tag pointing at `HEAD` is exactly `v<version>`.
- Every released heading other than the newest carries a `v` tag. The newest is
  the one exemption, because the commit that cuts a release exists before the tag
  that names it does; the next release brings it under the rule.

So a release is one commit that renames `[Unreleased]` to the new version, sets
`version` and both manifests to match, and is then tagged `v<version>`.

`make release` is the pass before that commit. It sends every bullet under
`[Unreleased]` to the judge in one call and names the bullets that must not ship
beside each other — two bullets describing one change, a bullet a later one
supersedes, a bullet under the wrong kind — and then runs the version gate. It
rewrites nothing and it needs the network, so it sits outside `check`.

## Calibrating the judge

The gates hold the tree; `make calibrate` holds the judge. It asks the
configured model about two record files in the `path:line<TAB>text` form
`--lines` reads — one of lines a judge is expected to flag, one of lines it is
expected to pass — and prints how many of each it got, then every line the two
disagree about:

```sh
make calibrate TRIVIA=corpus/trivia.txt CLEAN=corpus/clean.txt
make calibrate TRIVIA=corpus/trivia.txt CLEAN=corpus/clean.txt CALIBRATE='--gate comments'
```

`--gate` chooses whose prompt is asked — `md`, `comments` or `changelog` — and `--model` asks a
model other than the configured one, which is how a prompt or a model change is
measured before it lands. It spends one call per 50 lines and needs the network,
so it sits beside `make trivia`, outside `check`.

## The calibration corpus

`scripts/gates/check_corpus.py` holds the files `make calibrate` reads. Two
rules: every line of every `corpus/*.txt` parses as `path:line<TAB>text`, and
across each label pair — `trivia.txt` with `clean.txt`,
`changelog-trivia.txt` with `changelog-clean.txt` — no text appears on both
sides.

Both failures are silent otherwise. A record that does not parse is dropped by
the reader rather than refused, so a run measures a smaller corpus than the file
states and reports a rate over it. A line filed under both labels is a
disagreement inside the answer key: the judge is scored wrong whichever verdict
it returns, and the run cannot report better than one error. The comparison is
over the record's text alone, since the same sentence cited from two files is one
claim about that sentence.

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
  reason in `PRECOMMIT_EXEMPT`, and a reason naming no gate fails as stale. The
  duplication gate is an `npx jscpd` invocation rather than a script under
  `scripts/gates/`, so a filename sweep cannot find it: that invocation is named
  in the gate and required in both configs by the same rule. Its whole scope is
  the `path` list in `.jscpd.json`, and every entry there names a directory the
  tree tracks — jscpd walks what it is given and prints a percentage over what it
  found, so a renamed directory reads as a clean tree rather than as a gate that
  stopped looking.

A new gate is wired into both the `lint` target and `.pre-commit-config.yaml` in
the change that adds it, and holds to the standard it polices: mypy strict, the
ruff set in `pyproject.toml`, and `ruff format` at 120 columns. `scripts/` is inside
mypy's and vulture's paths and outside `--cov=triviajudge`, so a gate carries no
coverage obligation.

## Licence

Contributions are under the MIT licence, the same as the project.
