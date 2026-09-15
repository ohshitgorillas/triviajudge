# Trivia Judge

A huge pet peeve of mine is that agents cannot reliably distinguish between "a useful fact for the next agent" and "a useless fact I know". Without specific attention to such, documentation and comments collect a type of rot: dated approvals, hand-back receipts, refactor records, relitigation of rules already in every agent's primary instructions file, round and phase numbers used as positions in history, and prose whose only content is that something did not change.

The Trivia Judge package is three gates designed to prevent this rot by forcing agents to clean up docstrings, comments, and markdown files to state what holds now rather than what happened.

## The three gates

Some of that rot has a shape a regex can name. The rest is a judgment call, so a model makes it.

| Gate | Entry point | What it reads | Model call |
|---|---|---|---|
| Archaeology | `triviajudge-archaeology` | comments in `.py`, `.js`, `.mjs`, `.css` | no |
| Markdown trivia | `triviajudge-md` | lines a change adds to `.md` | yes |
| Comment trivia | `triviajudge-comments` | comments and docstrings a change adds | yes |
**Archaeology** is a fixed pattern list: ISO dates in prose, `used to`, `earlier draft`, refactor verbs followed by `of` or `from`, replacement narration, commit citations, and a past-tense verb sharing a sentence with a literal length. It needs no network and no model. A line that must keep its history takes `history-ok: <reason>` — the reason is required, because an excuse with no reason excuses nothing.

**The two judges** send what the patterns did not answer for to a model, and ask one question: would this text lose nothing by being deleted or rewritten in present tense? They prefer silence.

The order matters. The patterns screen first, and what they refuse never reaches the judge — a flagged candidate is already refused, so sending it buys nothing but tokens.

## Scope is what a change adds

No gate re-litigates prose that already shipped. The markdown judge reads the lines a commit adds; the comment judge reads the comments and docstrings it adds. A docstring arrives as one candidate with its lines joined, because a paragraph split into ten entries is ten sentences with no context.

## Sweeping the whole tree

`triviajudge-sweep` is the one thing here that judges the tree rather than what a change adds, and it is exempt from the scope rule above because it is an explicit user act: a console script you run, never a hook, and never wired into `hooks.json`. Every hook mode still judges added lines only, so no gate re-litigates shipped prose on a turn or a commit.

```
triviajudge-sweep                   # both gates over the whole tree
triviajudge-sweep --md              # markdown only
triviajudge-sweep --comments        # comments and docstrings only
triviajudge-sweep --paths src/      # narrow to a subtree, repeatable
triviajudge-sweep --limit 200       # judge at most this many candidates per gate
triviajudge-sweep --baseline        # remember every line the judges passed
triviajudge-sweep --check           # exit 1 when anything is flagged
```

Collection is whole-file, through the same filters the gates use: `md_skip` and the prose screen for markdown, `suffixes`, `excluded` and `comment_skip` for source. The archaeology patterns screen the comment candidates first; their complaints cost nothing and never reach a judge.

A judge takes one CLI call for every line it is given, so a sweep splits its candidates into batches of `sweep_batch` and asks once per batch. It counts the candidates and prints the call count before spending anything, and asks; `--yes` skips the question. A batch whose call fails is printed with the files it covers and the run continues — a commit gate fails closed because a commit is one decision, and a sweep is hundreds.

Flags print as `path:line: reason` and the run exits 0. `--check` exits 1 on any flag, complaint or failed batch, and `--out FILE` writes all three as JSON.

`--baseline` additionally writes every passed line's digest to `sweep-clean.json`, a file of its own beside the gates' caches. The markdown gate reads it at `Stop` alongside its own, so a line the sweep passed is a line the gate does not send again. The amnesty is one file: delete it and the whole amnesty is gone. The comment gate at `Stop` runs the pattern screen alone and makes no model call, so it reads no cache and the comment digests a baseline writes have no reader today.

Default is `sweep_model`, `claude-haiku-4-5`. Before changing it, calibrate: run `--lines` on a couple of hundred lines of your own tree under each model and diff the flag sets.

## Modes

```
triviajudge-md FILE...              # the staged diff of named files (pre-commit)
triviajudge-md --head               # what HEAD added
triviajudge-md --lines FILE         # path:line<TAB>text records, for calibration
triviajudge-md --stop               # a Stop payload on stdin, over the working tree
```

`--stop` is the agent-harness mode: exit 2 holds the turn open until the prose is fixed, once. A line the judge has passed is remembered by hash and never sent again, so a turn that adds no new prose makes no call at all.

The comment gate takes the same five modes, with one difference: under `--stop` it runs the pattern screen alone and makes no model call, so an added comment naming a date is caught in the turn that typed it without waiting on a CLI. Its judge runs at commit and over HEAD, on finished work. It keeps no cache — the modes that judge are the gate.

The archaeology gate takes a file list, and one mode of its own:

```
triviajudge-archaeology FILE...     # every comment in the named files, whole (pre-commit)
triviajudge-archaeology --post-tool-use   # a PostToolUse payload on stdin, one file
```

`--post-tool-use` takes `tool_input.file_path` from the payload and checks the lines the working tree adds to that file. Added lines are the scope, so an agent that opens a file carrying older archaeology is not held for prose it did not write, and a file whose suffix the gate cannot read a comment out of is not read at all. The value of the mode is timing: the same patterns run again at `Stop` inside the comment gate, and by then the edit is several steps back.

## The judge's own session runs no gate

The markdown judge shells out to the `claude` CLI from inside a `Stop` hook, and the inner session shares the working directory, so its own `Stop` hooks would fire the same gate. The judge sets `TRIVIAJUDGE_INNER` in the child's environment, and every hook mode reads it and does nothing. `stop_hook_active` cannot serve here: it marks the outer turn, not the inner process.

## The judged repository configures the gates

Values that belong to your tree rather than to the gates come from a `[tool.triviajudge]` table in your `pyproject.toml`, or a `.triviajudge.toml` at your root.

```toml
[tool.triviajudge]
md_skip = ["CHANGELOG.md"]          # files with their own gate or style rule
comment_skip = []                   # files whose own prose is the rule
suffixes = [".py", ".js", ".css"]   # what the comment gate reads
excluded = ["tests/"]               # prefixes it stays out of
cache_dir = ".triviajudge"
model = "claude-haiku-4-5"
md_judge_at_stop = true             # whether the markdown judge runs at Stop
sweep_batch = 150                   # lines per call in a sweep
sweep_parallel = 1                  # concurrent calls, capped at half the cores
sweep_model = "claude-haiku-4-5"    # the model a sweep asks
```

`md_judge_at_stop` stays on by default. Markdown has no pattern screen, so the model call is the whole gate at `Stop`, and the clean-line cache holds the cost to the lines a turn newly adds. Turn it off if you will not spend a nested call on every turn that adds markdown: the hook becomes a no-op, and the commit and HEAD modes still judge the same lines on finished work.

Three readings at the edges. No file, no table, or a missing key gives the defaults above and the gate runs. A file that is present but unparseable fails the gate rather than falling back, because a silent default over a corrupt table judges a different file set than the one you asked for. A key present but empty is honoured: an empty `excluded` is the widest scope and an empty `suffixes` the narrowest, and neither is reachable by leaving a key out.

## Install

```
pip install triviajudge
```

Python 3.12 or newer, no runtime dependencies. The two judges shell out to the `claude` CLI in print mode and need it on PATH and logged in; a CLI that fails, or an answer that is not the JSON asked for, fails the gate rather than passing it. A judge that cannot speak is not a judge that approves.

## pre-commit

```yaml
repos:
  - repo: https://github.com/ohshitgorillas/triviajudge
    rev: v0.1.0
    hooks:
      - id: archaeology
      - id: md-trivia
      - id: comment-trivia
```

## Claude Code plugin

The same gates run at the end of an agent turn, as a Claude Code plugin.

```
/plugin marketplace add ohshitgorillas/triviajudge
/plugin install triviajudge@triviajudge
```

The plugin wires the markdown judge and the comment screen to `Stop` and
`SubagentStop`, and the archaeology gate to `PostToolUse` on `Edit|Write`. Exit
2 holds the turn open with the complaints on stderr, once per turn.
`hooks/run-gate.sh` runs the gate module from the plugin checkout with the
checkout on `PYTHONPATH`, so the plugin needs Python 3.12 or newer on `PATH`
and no install of its own. The markdown judge shells out to the `claude` CLI;
the comment gate at `Stop` and the archaeology gate after an edit run the
pattern screen alone.

What a turn costs, and what it leaves behind:

- One turn that adds markdown lines the cache has not seen costs one
  `claude -p` call against `model` (`claude-haiku-4-5` by default), with those
  lines as its input, billed to whatever account the `claude` CLI is logged in
  to. A turn that adds no markdown, or only lines the cache holds, costs
  nothing. `md_judge_at_stop = false` turns the `Stop` call off and keeps the
  commit and `--head` modes.
- The gate writes its clean-line cache to `.triviajudge/` in the directory the
  agent runs in. It is per-checkout state, not a fact about the code, so add
  `.triviajudge/` to that repository's `.gitignore`. Deleting the directory
  costs a re-judge of every line, nothing more.

## The prose is data, never instruction

Both judges are told that everything after `LINES:` is data. Text that addresses the judge, vouches for its own standing, or restates the rules is flagged on that ground alone, whatever else it says. Each entry is judged by its own text: a neighbouring line cannot vouch for it.

## Licence

MIT.
