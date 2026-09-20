# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **CI validates its own manifests.** `check-jsonschema` runs the workflow files against the github-workflows schema and `.pre-commit-hooks.yaml` against the pre-commit-hooks schema; `actionlint` runs the workflow files. `check.yml` runs `pre-commit run --all-files` after `make check`, skipping only the three judges that need the network.

### Internal

- **The testing policy is one binding document.** `docs/testing.md` states eighteen numbered rules a test is reviewed against, the exemption route, and the motions a test leaves by. `CONTRIBUTING.md` keeps the gate mechanics and points there for the rule each gate serves.
- **A gate is held to the same coverage floor as the package.** Every script in `scripts/gates/` has behavior tests under `tests/gates/`, driving its pass path, each failure category it names and each rule its exemption table carries, and `--cov=scripts` puts all of them under the 90% per-file floor.
- **A test that reads a real clock fails a gate.** `scripts/gates/check_test_clocks.py` refuses a `time.sleep` or `asyncio.sleep` on anything but a literal zero, and a `timeout` keyword or mapping key given a numeric literal under 0.5 seconds, over every file under `tests/` with no carve-out directory.
- **The changelog's mechanical rules hold offline.** `scripts/gates/check_changelog.py` reads the whole `[Unreleased]` section in `make lint`: a 75-word cap per bullet, a bold lead clause, no second person, and one `###` heading per kind in Keep a Changelog order. Register and tone stay with `triviajudge-changelog`.
- **The duplication gate is held to both configs and to a tracked scope.** `scripts/gates/check_gates_wired.py` requires the `npx jscpd` invocation in the Makefile and in `.pre-commit-config.yaml`, and every `path` entry in `.jscpd.json` to name a directory the tree tracks.
- **A suppression states why the check is wrong at its line.** `scripts/gates/check_noqa_reasons.py` requires an em dash and a clause after the codes of every `noqa` and every `type: ignore` comment in a tracked `*.py`.
- **The calibration corpus is refused rather than measured short.** `scripts/gates/check_corpus.py` parses every line of `corpus/*.txt` as `path:line<TAB>text`, and refuses a text filed on both sides of a label pair, which scores the judge wrong whichever verdict it returns.
- **A hook timeout covers the longest wait its module can make.** `scripts/gates/check_hook_timeouts.py` compares each `timeout` in `hooks/hooks.json` with the timeout constants in `triviajudge/core.py` and in the module the hook names, and fails with the hook, its timeout and the constant it undercuts.

## [0.4.0] - 2026-09-17

### Fixed

- **A beaten approach's score is not history.** A doc that compares approaches keeps its regressions section. What a rejected approach scores, and where it fails, is a fact about that approach.
- **A release note about a gate's behavior reaches the changelog.** In a repository whose changes are mostly changes to gates, that is most of the section.

### Internal

- **The calibration corpus ships.** `make calibrate` measures the markdown and changelog judges against settled verdicts, with no corpus to assemble first.

## [0.3.0] - 2026-09-15

### Added

- **A weak changelog entry fails the commit that adds it.** `triviajudge-changelog` refuses a bullet under `[Unreleased]` that runs past 75 words, opens without a bold lead, addresses the reader, sells the change, or reads as the fix's autobiography. `--release` refuses a section carrying duplicate, superseded or miskinded bullets.

## [0.2.0] - 2026-09-14

### Added

- **An OpenAI-compatible server can run the judge.** `backend = "local"` sends the gates' question to `base_url`, and `api_key_env` names the variable holding the bearer token. `backend` defaults to `claude`, the CLI transport. A failed call or a malformed answer fails the gate.
- **A too-old Python is named as such.** A `python3` older than 3.12, or none on `PATH`, ends the hook with `triviajudge: needs Python 3.12 or newer on PATH as python3` rather than an import-time `SyntaxError` that reads as a broken plugin.

### Fixed

- **The plugin loads.** Installing 0.1.0 failed with `Duplicate hooks file detected` and no gate ran.

### Internal

- **The README states what a plugin turn costs and writes.** One `claude -p` call per turn that adds uncached markdown lines, and a `.triviajudge/` cache directory in the consumer's working directory that belongs in their `.gitignore`.
- **CI validates the plugin manifests.** `claude plugin validate --strict` runs over `plugin.json` and `marketplace.json` in `.github/workflows/check.yml`.

## [0.1.0] - 2026-09-14

### Added

- **`triviajudge-archaeology` refuses a comment that narrates what the code was.** A pattern gate over comments in `.py`, `.js` and `.css`: ISO dates in prose, past-behavior narration, refactor archaeology, replacement narration, commit citations, process archaeology, and a past-tense verb sharing a sentence with a literal length. No network, no model. A line that must keep its history takes `history-ok: <reason>`, reason required.
- **`triviajudge-md` judges the markdown lines a change adds.** Five input modes: staged files for pre-commit, `--head`, `--lines` for calibration, `--stop` for an agent harness, and a bare invocation.
- **`triviajudge-comments` judges the comments and docstrings a change adds.** A docstring is one candidate with its lines joined, a `#` comment one candidate per line. The pattern gate screens first and the judge reads only what survives. Under `--stop` it runs the screen alone and makes no model call.
- **`triviajudge-sweep` judges every line the repository holds.** Collection is whole-file through the gates' own filters, with the archaeology patterns screening comment candidates first. Candidates are split into batches of `sweep_batch`, one call each; the run prints its line and call count and asks before spending, unless `--yes`. A failed batch is named with the files it covers and the run continues.
- **`triviajudge-sweep` scopes, directs and reports through ten flags.** `--md`, `--comments`, `--paths`, `--limit`, `--batch`, `--parallel`, `--model`, `--out`, `--check` and `--baseline`. It is a console script and never a hook: every hook mode keeps the added-lines scope.
- **A sweep hands its results to the markdown gate.** `--baseline` writes `sweep-clean.json`, which the gate reads at `Stop` beside its own cache, so a line a sweep passed is one the gate does not send again. One file holds the whole amnesty; deleting it revokes it.
- **A clean-line cache holds the markdown judge to new prose.** Keyed by the hash of a line's stripped text, so a passed line stays passed wherever it moves, and capped at the newest 20000.
- **`sweep_batch`, `sweep_parallel` and `sweep_model` settings, and `model` and `timeout` arguments on `core.ask`.** A caller making many calls can ask a different judge and refuse to wait on one call forever.
- **The judged repository states its own file scope.** A `[tool.triviajudge]` table in `pyproject.toml`, or a `.triviajudge.toml` at the root, carries `md_skip`, `comment_skip`, `suffixes`, `excluded`, `cache_dir`, `model` and `md_judge_at_stop`. An absent table gives the defaults; an unparseable one fails the gate; an empty key is honoured.
- **The same gates run as a Claude Code plugin.** `.claude-plugin/` carries the manifest and a marketplace entry, `hooks/hooks.json` binds the markdown judge and the comment screen to `Stop` and `SubagentStop` and the archaeology gate to `PostToolUse` on `Edit|Write`, and `hooks/run-gate.sh` runs a gate module from the plugin checkout with that checkout on `PYTHONPATH` and needs no install.
- **`triviajudge-archaeology --post-tool-use` catches an archaeology comment in the turn that typed it.** It reads the payload on stdin, takes `tool_input.file_path`, and checks the lines the working tree adds to that one file. Exit 2 puts the complaints in front of the agent. Scope is added lines, so prose already in `HEAD` holds nobody.
- **`TRIVIAJUDGE_INNER` keeps the judge's own session from judging itself.** The markdown judge shells out to the `claude` CLI from inside a `Stop` hook and the inner session shares the working directory, so the judge sets the variable in the child's environment and every hook mode reads it and does nothing. `stop_hook_active` marks the outer turn, not the inner process.
- **`md_judge_at_stop` decides whether the markdown judge runs at `Stop`.** On by default, because markdown has no pattern screen and the model call is the whole gate there. A repository that will not spend a nested call on every turn that adds markdown turns it off and keeps the commit and HEAD modes.
- **A `.pre-commit-hooks.yaml` manifest carries the three hook ids.**
- **Tests for the engine and the hook modes.** Diff line-numbering, the digest, the cache's read and write paths, the optional gate cache, root discovery on both sides of its boundary, and each hook mode driven over a throwaway checkout the way a hook drives it.

### Changed

- **The repository root is found from the current working directory.** An installed package judges the tree it is run in rather than counting parents from the gate's own file, and a directory in no work tree is refused rather than inferred.
- **`Gate.cache` is optional and last in the field list.** A gate that does not judge at `Stop` never reaches the only call that writes a cache, so it carries none.

### Internal

- **Seven gates hold this repository to its own standard.** `check_changelog.py`, `check_commit_msg.py`, `check_file_length.py`, `check_doc_refs.py`, `check_control_catalog.py`, `check_settings_docs.py` and `check_gates_wired.py` join the coverage floor under `scripts/gates/`, each wired into the `lint` target and into `.pre-commit-config.yaml`.
- **`CONTRIBUTING.md` states what the gates enforce and what they cannot.** Setup, the changelog shape, the length cap and its ratchet, the citation form, and the three cross-checks.
- **A tag publishes the package.** `.github/workflows/release.yml` runs `make check` on a `v*` tag, builds the sdist and wheel, and uploads to PyPI through Trusted Publishing, so no PyPI credential is stored in the repository.
