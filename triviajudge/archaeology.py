#!/usr/bin/env python3
"""Gate: comments state live constraints, not decision archaeology.

A comment earns its keep by telling the next reader a constraint the code
cannot show. A comment that narrates what the code once did, when a decision
happened, or which iteration came before spends the reader's attention on
facts that help nobody make the next change — and each one invites the next.
This gate blocks the phrasing that reliably marks such narration:

- ISO dates in prose (``2026-07-28``) — a dated remark describes a moment,
  not an invariant;
- ``used to``, ``earlier draft/version/design`` and ``as it always was`` —
  past-behavior narration;
- ``extracted``/``split``/``moved``/``pulled``/``lifted``/``carved`` followed by
  ``of`` or ``from``, and ``reorg`` — refactor archaeology. Both prepositions,
  because a rule bound to one of them is a rule you clear by writing the other;
- ``this/that/which replaced`` — replacement narration;
- a past-tense verb sharing a sentence with a literal length (``the bar was
  45.5px``, ``put 48px between two packs``) — measurement archaeology, a number
  describing a layout that is gone. A live measurement is present tense and
  passes;
- conventional-commit citations (``fix(live): …``) — git already holds these;
- ``withdrawn`` / ``was reversed`` / ``process note`` — process archaeology.

What no pattern can catch is narration carrying neither a keyword nor a number
("the bar shipped four heights at once"). The list narrows the failure modes; it
does not decide the question for you.

Scope is shipped code and tooling comments. ``tests/`` is deliberately out of
scope — a regression test legitimately names the bug it pins, in whatever tense
the bug demands — and so is ``scripts/probes/``, whose scripts are session
records with dates as their content. ``CHANGELOG.md`` and vendored code are
excluded by the file list in the Makefile.

The fix is never to reword around the pattern: state the constraint that holds
NOW, in present tense, or delete the remark. History that must stay — an
upstream attribution, a pinned legacy behavior — takes ``history-ok:
<reason>`` on the offending line, reason required, same contract as the token,
class, card and dirty-mark gates.

Usage:

* ``triviajudge-archaeology FILE...`` checks every comment in the named files
  (pre-commit), where the file list is the scope and the whole file is read
* ``triviajudge-archaeology --post-tool-use`` reads a ``PostToolUse`` payload
  on stdin, takes ``tool_input.file_path`` from it, and checks the lines the
  working tree adds to that one file. Exit 2 puts the complaints in front of
  the agent in the turn that wrote them, which is the whole reason this mode
  exists: the same patterns run again at ``Stop`` inside ``comment_trivia``,
  and by then the edit is several steps back. Scope is added lines, so an
  agent that opens a file carrying older archaeology is not held for prose it
  did not write, and a file outside ``SUFFIXES`` is not read at all.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import tokenize
from pathlib import Path

from triviajudge.core import NotARepositoryError, added_lines, git, git_diff, inner_session, root

PRAGMA = "history-ok:"

#: The suffixes ``comment_lines`` knows how to read a comment out of. The file-list modes
#: trust the list they are handed and fall back to reading every line; the payload mode is
#: handed whatever the agent last wrote, so it reads these and nothing else.
SUFFIXES = (".py", ".js", ".mjs", ".css")

#: The gates whose own text is the rule: each spells out the phrases it refuses, so each
#: trips the rule it defines. Owner-approved skip list, the same three the judge skips.
RULE_HOLDERS = frozenset({"archaeology.py", "md_trivia.py", "comment_trivia.py"})

#: a literal length, and the past-tense verbs that turn one into a remark about
#: a layout that is gone. A live measurement takes the present tense ("the
#: shared text-input rule IS 28rem") and so is not matched.
_LENGTH = r"\d+(?:\.\d+)?(?:px|rem|em|ch|%)"
_PAST = r"(?:was|were|used|put|added|made|grew|shipped|jumped|sat|stood|became)"

PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b20[0-9]{2}-[01][0-9]-[0-3][0-9]\b"), "dated narration"),
    (re.compile(r"\bused to\b", re.IGNORECASE), "past-behavior narration"),
    (
        re.compile(r"\bearlier (?:draft|version|design)\b", re.IGNORECASE),
        "prior-iteration narration",
    ),
    (
        re.compile(
            r"\b(?:extracted|split|moved|pulled|lifted|carved|broken)\s+(?:out\s+|here\s+)?(?:of|from)\b",
            re.IGNORECASE,
        ),
        "refactor archaeology",
    ),
    (re.compile(r"\breorg\b", re.IGNORECASE), "refactor archaeology"),
    (
        re.compile(r"\b(?:this|that|which)\s+replaced\b", re.IGNORECASE),
        "replacement narration",
    ),
    (
        re.compile(r"\bas (?:it )?always (?:was|has been|did)\b", re.IGNORECASE),
        "past-behavior narration",
    ),
    (
        re.compile(r"\b(?:feat|fix|docs|test|chore|refactor)\([a-z0-9-]+\):"),
        "commit citation",
    ),
    (
        re.compile(r"\b(?:withdrawn|was reversed|process note)\b", re.IGNORECASE),
        "process archaeology",
    ),
    (
        re.compile(rf"\b{_PAST}\b[^.;]{{0,60}}{_LENGTH}|{_LENGTH}[^.;]{{0,60}}\b{_PAST}\b", re.IGNORECASE),
        "measurement archaeology",
    ),
)

#: a pragma with nothing after it — the form of an exemption nobody could justify
EXEMPT = re.compile(re.escape(PRAGMA) + r"\s*(?!\*/)\S")
BARE_PRAGMA = re.compile(re.escape(PRAGMA) + r"\s*(?:\*/\s*)?$")

#: `//` opens a comment unless it is the tail of a URL scheme
LINE_COMMENT = re.compile(r"(?<!:)//(.*)$")

REDIRECT = (
    "An archaeology comment narrates what the code was; a comment earns its\n"
    "keep by stating the live constraint. Rewrite it in present tense as the\n"
    "invariant that holds now, or delete the remark. History that must stay\n"
    f"(upstream attribution, pinned legacy behavior) takes `{PRAGMA} <reason>`\n"
    "on the offending line."
)


def python_comment_lines(text: str) -> list[tuple[int, str]]:
    """(line, text) for every comment and triple-quoted string line."""
    out: list[tuple[int, str]] = []
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type == tokenize.COMMENT:
            out.append((tok.start[0], tok.string))
        elif tok.type == tokenize.STRING and tok.string.lstrip("rbuRBU").startswith(('"""', "'''")):
            for offset, line in enumerate(tok.string.splitlines()):
                out.append((tok.start[0] + offset, line))
    return out


def block_comment_lines(text: str, *, line_comments: bool) -> list[tuple[int, str]]:
    """(line, text) for `/* … */` blocks, plus `//` comments when asked."""
    out: list[tuple[int, str]] = []
    in_block = False
    for lineno, line in enumerate(text.splitlines(), 1):
        rest = line
        if in_block:
            head, closed, rest = rest.partition("*/")
            out.append((lineno, head))
            if not closed:
                continue
            in_block = False
        while "/*" in rest:
            rest = rest.split("/*", 1)[1]
            body, closed, rest = rest.partition("*/")
            out.append((lineno, body))
            if not closed:
                in_block = True
                break
        else:
            if line_comments and (match := LINE_COMMENT.search(rest)):
                out.append((lineno, match.group(1)))
    return out


def comment_lines(path: Path) -> list[tuple[int, str]]:
    """Return (line, text) for every comment in the file, read the way its suffix demands."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        return python_comment_lines(text)
    if path.suffix in {".js", ".mjs"}:
        return block_comment_lines(text, line_comments=True)
    if path.suffix == ".css":
        return block_comment_lines(text, line_comments=False)
    return list(enumerate(text.splitlines(), 1))


def line_complaints(path: Path, lineno: int, text: str) -> list[str]:
    """What one comment line is held for: a reasonless pragma, else every archaeology phrase in it."""
    if BARE_PRAGMA.search(text):
        return [f"{path}:{lineno}: bare `{PRAGMA}` — the reason is required"]
    if EXEMPT.search(text):
        return []
    found = [(pattern.search(text), label) for pattern, label in PATTERNS]
    return [f'{path}:{lineno}: {label} ("{match.group(0)}")' for match, label in found if match]


def check_file(path: Path, only: set[int] | None = None) -> list[str]:
    """Return one complaint per archaeology phrase or reasonless pragma; ``only`` narrows it to those lines."""
    complaints: list[str] = []
    for lineno, text in comment_lines(path):
        if only is None or lineno in only:
            complaints.extend(line_complaints(path, lineno, text))
    return complaints


def added(rel: str) -> set[int] | None:
    """Line numbers the working tree adds to one repo-relative path; None when every line is added."""
    try:
        if not git("ls-files", "--", rel).strip():
            return None
        return {line.number for line in added_lines(git_diff("HEAD", "--", rel))}
    except subprocess.CalledProcessError:
        return None


def named(payload: dict[str, object]) -> str | None:
    """The path a ``PostToolUse`` payload names, when its ``tool_input`` carries one."""
    given = payload.get("tool_input")
    name = given.get("file_path") if isinstance(given, dict) else None
    return name if isinstance(name, str) and name else None


def target(payload: dict[str, object]) -> Path | None:
    """The file a ``PostToolUse`` payload names, when it is one this gate reads inside this repository."""
    name = named(payload)
    if name is None:
        return None
    path = Path(name)
    if path.suffix not in SUFFIXES or path.name in RULE_HOLDERS:
        return None
    path = (root() / path).resolve()
    if not path.is_file() or not path.is_relative_to(root().resolve()):
        return None
    return path


def payload() -> dict[str, object] | None:
    """The ``PostToolUse`` payload on stdin, or None when stdin carries no object."""
    try:
        given = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return None
    return given if isinstance(given, dict) else None


def added_complaints(given: dict[str, object]) -> list[str]:
    """What the lines the working tree adds to the payload's file are held for; empty when it is unreadable."""
    try:
        path = target(given)
        if path is None:
            return []
        rel = str(path.relative_to(root().resolve()))
        return check_file(path, added(rel))
    except NotARepositoryError:
        return []
    except (OSError, UnicodeDecodeError, SyntaxError, tokenize.TokenError) as exc:
        print(f"{given.get('tool_input')}: not read ({exc})", file=sys.stderr)
        return []


def post_tool_use() -> int:
    """Check the lines the working tree adds to the file the payload on stdin names."""
    if inner_session():
        return 0
    given = payload()
    if given is None:
        return 0
    complaints = added_complaints(given)
    if not complaints:
        return 0
    for complaint in complaints:
        print(complaint, file=sys.stderr)
    print(f"\n{REDIRECT}", file=sys.stderr)
    return 2


def checked(names: list[str]) -> list[str]:
    """What the named files are held for, skipping the three gates that spell the blocked phrases out.

    Those three modules are where the rule text keeps its examples; the skip list is owner-approved.
    """
    complaints: list[str] = []
    for name in names:
        path = Path(name)
        if path.is_file() and path.resolve().name not in RULE_HOLDERS:
            complaints.extend(check_file(path))
    return complaints


def main() -> int:
    """Refuse a comment narrating the code's history instead of a constraint that holds now."""
    parser = argparse.ArgumentParser(description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*", help="source files to check whole (pre-commit)")
    parser.add_argument("--post-tool-use", action="store_true", help="read a PostToolUse payload on stdin")
    args = parser.parse_args()
    if args.post_tool_use:
        return post_tool_use()
    complaints = checked(args.files)
    for complaint in complaints:
        print(complaint)
    if complaints:
        print(f"\n{REDIRECT}")
    return 1 if complaints else 0


if __name__ == "__main__":
    sys.exit(main())
