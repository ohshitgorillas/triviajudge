# Testing policy — binding for all contributors, human or agent

A violation is rejected in review even when the suite is green. Rule numbers are stable: a new rule goes at the end or takes a letter, nothing is renumbered. The current suite under `tests/` predates this file and is not precedent; a test in it that breaks a rule leaves through the `/tests` chain, never by hand edit.

## Core rules

1. **Test behavior, never implementation.** This diff, this stdin payload, this reply from the model; the gate prints this and exits with that. A refactor that keeps behavior and breaks a test has found a defective test. Module layout, private helpers, call order, log text: off limits.

2. **One assertion per test.** One `assert` or one `pytest.raises` per `test_` function. Two facts that are one behavior compare as a tuple: `assert (finished.returncode, finished.stderr) == (0, "")`. Sweeps are `@pytest.mark.parametrize`, never assert-in-loop, never `all()`/`any()`. A conjunction is one assertion per operand; `x is not None and x["k"] == v` is repaired as `(x or {})["k"] == v`. `scripts/gates/suite/check_test_assertions.py`.

3. **Public API only.** A test reaches the package the way a hook, a pre-commit run or `python -m` does. No `_private` attribute, no monkeypatch inside `triviajudge/`. `_ask_cli`, `_ask_http`, `_answer`, `_headers` are reached through `ask` and a wire fake, never called.

4. **Fakes speak the wire protocol; mocks of our own code are forbidden.** Four wires, one fake each:
   - `claude` CLI: a fake executable named `claude` on a `PATH` the test builds, printing the real print-mode envelope, real stderr, real exit code, quirks included (`is_error` envelope, non-zero exit with the message on stdout). `core.binary` resolves by name, so `PATH` is the seam.
   - HTTP backend: an `http.server` thread on an OS-chosen port answering real Messages-API JSON, `poll_interval=0.01` so teardown is prompt.
   - `git`: never faked. A throwaway repository under `tmp_path`, real commits, real `git`.
   - Hook harness: the gate module spawned with the payload on stdin and an environment the test built from nothing plus `coverage_environment()`.
   Never `monkeypatch.setattr(core, "ask", ...)`, never stub `subprocess.run` or `urlopen`.

5. **Anchor on contract facts, never golden dumps.** `flags[0]["line"] == 7`, never a whole report or envelope against a snapshot.

6. **Test names state behavior.** `test_stop_mode_exits_zero_on_second_run`, not `test_stop_2`.

7. **No test waits on a wall clock.** A retry or timeout is judged by what it concluded, never by how long it took.
   - The timeout path is driven by a fake `claude` that raises or exits, never by sleeping through a small deadline. A fake never sleeps; the one legal sleep is the literal `0`.
   - No carve-out: there is no e2e lane, and `tests/e2e/` is not created as a route around this rule. `scripts/gates/suite/check_test_clocks.py` reads every file under `tests/`: a `sleep` on anything but `0`, and a `timeout` or `*_timeout` literal under 0.5 s, fail it.
   - Gated: `scripts/gates/suite/check_suite_time.py` holds `make test` wall time to the last green run's; over 5 s slower needs `--accept`, 10 s or more is refused. `scripts/gates/repo/check_hook_timeouts.py` holds each hook `timeout` at or above the largest constant its module can reach.

8. **New tests must bite.** Red against pre-change code, with implementation reverted to `HEAD` and tests kept. Only an assertion failure is bite; a collection or import error is no evidence. A new surface with no red run possible: the spec block names the null stub each line fails against. Characterization and pure-refactor tests are exempt, and the exemption is said in the hand-back, never assumed.

9. **Assert only what the test put on the wire, wire identifiers, and numbers derived from wire data. Every string born under `triviajudge/` or `scripts/` is copy.** The test: would the writer have to read the implementation to know this literal? Then it stays out of the assertion and out of `match=`.
   - A refusal is matched on what the test seeded: `match="no credit"` where the fake wrote `no credit`, never `match="claude exited 1: no credit"`.
   - A gate's report line is copy. Assert the exit code and the `path:line` the test constructed, never the wording after it.
   - The prompt is copy. A test asserts that its own lines reached the fake, never a fragment of the prose around them.
   - `corpus/` is calibration data, read by `make calibrate`, never by the suite. Whether it is well-formed is `scripts/gates/repo/check_corpus.py`, a data gate.
   - A curated count is copy: the number of patterns in a screen is data, the number of lines a diff added is contract.
   - `scripts/gates/suite/check_no_copy_assertions.py` refuses an unseeded literal of two or more words. Nothing left once the wording goes: strike, do not keep.

10. **A test discriminates, or it is a tautology.** Name an implementation that fails the assertion and one that passes, both plausible; if the failing one is only "feature absent", the test pins presence. Shapes that fail:
    - One input, one absolute value: a lookup-table entry. Assert a relation, or two distinct expected values on one surface.
    - Existence in place of value (truthy, `is not None`, type, length, key presence): legal only as an owner-approved `EXEMPT` entry with a reason.
    - A value the absent feature also produces: `0`, `None`, `""`, `[]`, exit `0` from a gate that never ran, an empty flag list from a judge never asked.
    - The fix's own mechanism: a helper called, a field set, a cache file present. Rule 1 by another name.
    - A writer round-tripped through its own reader: `remember_clean` checked through `clean_cache`. Pin one half against a digest computed from a line the test wrote.
    - Expected value computed the way the code computes it. Write the number.
    - A pattern screened only on the phrase it was written from. Each pattern carries one positive that is not its source phrase and one negative sharing words with it.

11. **A test guards against a bug, never a change of mind.** Write the bug report its failure would file; if only a decision change turns it red, reshape to the invariant or delete.
    - A limit is tested at the limit and one over, never as the literal `75`. An order is tested as "this before that" at two orderings, never as the list.
    - A default (model, timeout, cache path) is tested by role: unset reads it, a `[tool.triviajudge]` key overrides it.
    - Exit codes `0` and `2` are the hook contract and are pinned. Which non-zero a CLI error maps to is not, unless a documented consumer branches on it.
    - Column alignment, key order in the cache file, the spelling of a number: not asserted unless a consumer parses it.
    - The tell: a fixture-supplied value is asserted verbatim; a design-chosen value never absolutely.

12. **A test costs.** A test constraining nothing another does not is deleted, and deletion is not a coverage regression. Two tests that cannot fail independently are one test. A test written to reach a line is rule 1 by another route: fix the code. `scripts/gates/suite/check_coverage_floor.py` holds 90% per file as a floor, never a target.

13. **Fakes answer from tables, never logic.** The fake `claude` prints the envelope the test wrote for this case. A fake that reads the prompt and decides what to flag is a second judge.

14. **Helpers return values.** No `assert` outside a `test_` function; a fixture that must refuse raises. `scripts/gates/suite/check_test_assertions.py`.

15. **Lowest lane.** Pure function (`added_lines`, `flags_from`, `parsed`), then `ask` against a wire fake, then a gate driven in process, then a gate spawned with stdin. A spawned test an in-process test already covers is deleted; spawning is for what only the boundary shows: stdin, exit code, scrubbed environment, `INNER`.

16. **No environment coupling.** No real `HOME`, `PATH`, cwd, git config, fixed port, locale or timezone. A spawned gate's environment is built from nothing plus the coverage variables. Green on one machine and red on another is this rule.

17. **A warning is a failure.** `filterwarnings = ["error"]` stays; an unclosed handle or a deprecation is a defect, never a filter.

18. **The suite never leaves the machine.** No network, no real `claude`, no API key. `make test` passes with neither installed. What needs them is `make calibrate`, not a test.

## Speed is a correctness property

`make test` runs on every commit. A test that waits on a wall clock is struck on sight; coverage is not a defense. What it pinned is re-pinned fast through the spec lane, or stays unpinned.

## Exemptions

An exemption lives in the `EXEMPT` table of the gate that would report the site, keyed `<path>::<test name>`, reason naming the condition that removes it. Only the existence and skip categories may be exempted. Owner-approved: a contributor proposes it in the hand-back and does not add it. `skip`, `skipif` and `xfail` are exemptions; `xfail_strict = true` stays. `importorskip` on a dev-extra tool is mechanism, not exemption. Every `noqa` and `type: ignore` under `tests/` carries an em dash and a clause, as `scripts/gates/code/check_noqa_reasons.py` holds the package to.

## Motions

No hand edits `tests/`. A test breaking a rule leaves as `motion: strike` citing the rule and quoting the assertion; one that pins behavior worth keeping goes as `motion: amend`; one whose assertion stays byte-identical while the code around it moves goes as `motion: rehome`; one pinning behavior the owner dropped goes as `strike` with `removed:` quoting the block's `brief:`. Line shapes and merge checks live in the gauntlet plugin's `docs/testing.md`. The `arbiter` cites core rule numbers only; the sections after the core rules carry no citable number.

## Mutation testing

Never a merge gate. `make mutate`, or `make mutate MUTATE='triviajudge.core.*'` for one module (fnmatch, trailing `.*` load-bearing). Scope is `[tool.mutmut]`, run `-x --no-cov`. A survivor is untested, equivalent, or dead: pick which, chase no score.

## Stack-specific addenda

- pytest, `testpaths = ["tests"]`, sweeps by `parametrize` with `ids=` in plain words. No JS suite; `node_modules` holds jscpd alone.
- Gates are modules by filename. `tests/gates/conftest.py` puts `scripts/gates/` on `sys.path`; `written(name, source)` writes a fixture module relative to cwd, because gates read a path as the tree it sits in. Such a case runs from `tmp_path` under `monkeypatch.chdir`.
- A spawned gate is measured only through `COVERAGE_PROCESS_START` and `COVERAGE_FILE`; a spawn that drops them runs unmeasured and fails the floor for no reason the report names.
- `INNER` is a wire fact: set it in the built environment, never patch `inner_session`.
- `scripts/calibrate.py` and `scripts/metrics/` are outside the suite and the floor. That gap is stated here, not closed with a test that reaches the network.
