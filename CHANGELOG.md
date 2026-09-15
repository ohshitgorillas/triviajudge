# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
