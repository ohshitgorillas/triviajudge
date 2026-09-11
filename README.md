# Trivia Judge

Three gates that hold the prose a change adds to what holds now, rather than what happened.

Documentation and comments collect a particular kind of rot: dated approvals, hand-back receipts, refactor records, round and phase numbers used as positions in history, corrections that narrate the mistake they fix, and prose whose only content is that something did not change. None of it helps the next reader make the next change, and each piece invites the next.

Some of that has a shape a regex can name. The rest is a judgment call, so a model makes it.

## The three gates

| Gate | Entry point | What it reads | Model call |
|---|---|---|---|
| Archaeology | `triviajudge-archaeology` | comments in `.py`, `.js`, `.css` | no |
| Markdown trivia | `triviajudge-md` | lines a change adds to `.md` | yes |
| Comment trivia | `triviajudge-comments` | comments and docstrings a change adds | yes |

**Archaeology** is a fixed pattern list: ISO dates in prose, `used to`, `earlier draft`, refactor verbs followed by `of` or `from`, replacement narration, commit citations, and a past-tense verb sharing a sentence with a literal length. It needs no network and no model. A line that must keep its history takes `history-ok: <reason>` — the reason is required, because an excuse with no reason excuses nothing.

**The two judges** send what the patterns did not answer for to a model, and ask one question: would this text lose nothing by being deleted or rewritten in present tense? They prefer silence.

The order matters. The patterns screen first, and what they refuse never reaches the judge — a flagged candidate is already refused, so sending it buys nothing but tokens.

## Scope is what a change adds

No gate re-litigates prose that already shipped. The markdown judge reads the lines a commit adds; the comment judge reads the comments and docstrings it adds. A docstring arrives as one candidate with its lines joined, because a paragraph split into ten entries is ten sentences with no context.

## Modes

```
triviajudge-md FILE...              # the staged diff of named files (pre-commit)
triviajudge-md --head               # what HEAD added
triviajudge-md --lines FILE         # path:line<TAB>text records, for calibration
triviajudge-md --stop               # a Stop payload on stdin, over the working tree
```

`--stop` is the agent-harness mode: exit 2 holds the turn open until the prose is fixed, once. A line the judge has passed is remembered by hash and never sent again, so a turn that adds no new prose makes no call at all.

The comment gate takes the same five modes, with one difference: under `--stop` it runs the pattern screen alone and makes no model call, so an added comment naming a date is caught in the turn that typed it without waiting on a CLI. Its judge runs at commit and over HEAD, on finished work. It keeps no cache — the modes that judge are the gate.

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
```

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

## The prose is data, never instruction

Both judges are told that everything after `LINES:` is data. Text that addresses the judge, vouches for its own standing, or restates the rules is flagged on that ground alone, whatever else it says. Each entry is judged by its own text: a neighbouring line cannot vouch for it.

## Licence

MIT.
