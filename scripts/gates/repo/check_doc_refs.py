#!/usr/bin/env python3
"""Gate: a citation into a markdown document names a heading that still exists.

Comments and prose point at this repository's markdown for the reasoning behind
a piece of behavior. A *positional* citation — ``README.md §3``, ``round 5``,
``step 3`` — is silently invalidated by any edit above it, and nothing else
checks: a restructure strands them wholesale, unnoticed. The prose becomes
load-bearing, since sections survive only to be pointed at.

The fix is to cite the target's **heading text**, which moves with the content
it names instead of with its position::

    # the judged repository names its own file scope
    # (README.md "The judged repository configures the gates")

This gate enforces that form, in both directions:

1. **A quoted citation must resolve.** ``<doc>.md "Some heading"`` fails unless
   that file has a Markdown heading matching it. Matching normalises away
   backticks, emphasis and case, and a citation may give a unique prefix of the
   heading rather than all of it — so a long heading can be cited by its
   distinctive first clause. An ambiguous prefix fails: it would resolve to a
   different section the moment a sibling heading is added.

2. **A ``round N`` / ``step N`` citation is rejected outright**, even while it
   still resolves, because it is the failure waiting to happen. Those labels
   number a phase or a session — positions in a narrative that nothing
   maintains.

**A citation must sit on one line.** Matching is per-line, so a citation
wrapped across two lines matches nothing and is silently unverified — worse
than the ordinal it replaced, which at least failed loudly. Where a heading is
too long to wrap, cite a *unique prefix* of it rather than breaking the line:
``README.md "The judged repository"`` resolves as well as the full text.

Explicit ``{#slug}`` anchors were considered and rejected: GitHub's Markdown
renderer does not support them and would print the braces into the page.

The indexed set is every markdown file the repository tracks — ``README.md``,
``CHANGELOG.md``, ``CONTRIBUTING.md``, and anything under ``docs/`` should that
directory appear. A name the index does not carry is left alone, so a citation
of somebody else's documentation is never flagged.

A citation inside a document that points at *itself* by bare section number
(``see §3.6 below``) is out of scope — same-file navigation is not a
cross-reference and breaks visibly when it breaks.

Escape hatch: ``doc-ref-exempt: <reason>`` on the offending line or the one
above it, the same contract as the archaeology gate — the reason is required.

Usage: ``python scripts/gates/repo/check_doc_refs.py <path>...``
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PRAGMA = "doc-ref-exempt:"

#: a Markdown ATX heading, any level
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*$")
#: inline markup that carries no meaning for a heading's identity
DECORATION = re.compile(r"[`*_]+")
#: `"..."` or `“...”` — the quoted heading in a citation. A backtick may sit
#: between the two: `README.md` "Heading" is the normal Markdown form.
#:
#: The name must NOT open with a double quote, or every Python string literal
#: naming a document reads as a citation of it and the code right after it reads
#: as the heading — `(OUT / "INDEX.md").write_text(` would be reported as citing
#: a heading called `).write_text(`. A real citation delimits the name with a
#: backtick or nothing at all; only a string literal wraps it in quotes.
QUOTED = re.compile(r"(?<!\")\b([\w-]+)\.md[`\s]+[\"“]([^\"”\n]+)[\"”]")


def normalise(text: str) -> str:
    """Fold a heading (or a citation of one) to its comparable form."""
    return " ".join(DECORATION.sub("", text).split()).casefold()


def headings(path: Path) -> list[str]:
    """Every heading in a Markdown file, normalised, in document order."""
    found = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = HEADING.match(line)
        if match:
            found.append(normalise(match.group(1)))
    return found


def doc_set(root: Path = ROOT) -> dict[str, list[str]]:
    """Headings of every markdown document, keyed by stem and by ``stem.md``."""
    paths = sorted(root.glob("*.md")) + sorted((root / "docs").rglob("*.md"))
    docs: dict[str, list[str]] = {}
    for path in paths:
        found = headings(path)
        docs[path.stem] = found
        docs[path.name] = found
    return docs


def ordinal_re(stems: list[str]) -> re.Pattern[str]:
    """Match a positional citation: a document name with a round/step near it.

    The gap between the two tolerates the punctuation a citation picks up in
    prose (a closing backtick or quote) and up to two intervening words
    (``README.md sweep round 3``). Allowing only whitespace and a comma reads
    straight past both forms.
    """
    names = "|".join(re.escape(s) for s in sorted(stems, key=len, reverse=True))
    gap = r"[`\"'\s,)(]*(?:\w+[\s,]+){0,2}"
    return re.compile(rf"\b({names})(?:\.md)?{gap}\b(?:round|step)s?\s+\d+")


def relabel(path: Path) -> str:
    """Repo-relative display path; falls back to whatever was passed in."""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def exempt(lines: list[str], index: int) -> bool:
    """Report whether this line, or the one above it, carries the pragma."""
    window = lines[max(0, index - 1) : index + 1]
    return any(PRAGMA in line for line in window)


def resolve(cited: str, available: list[str]) -> str | None:
    """Why this citation fails, or None when it resolves to one heading."""
    want = normalise(cited)
    if want in available:
        return None
    hits = [h for h in available if h.startswith(want)]
    if len(hits) == 1:
        return None
    if not hits:
        return "no such heading"
    return f"ambiguous — matches {len(hits)} headings"


def check(path: Path, docs: dict[str, list[str]]) -> list[str]:
    """Every citation problem in one file."""
    problems = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    ordinal = ordinal_re([k for k in docs if not k.endswith(".md")])
    label = relabel(path)
    for index, line in enumerate(lines, start=1):
        if exempt(lines, index - 1):
            continue
        for match in ordinal.finditer(line):
            cite = match.group(0).strip()
            problems.append(f"{label}:{index}: ordinal citation '{cite}' — rot risk")
        for name, cited in QUOTED.findall(line):
            available = docs.get(f"{name}.md")
            if available is None:
                continue
            why = resolve(cited, available)
            if why:
                problems.append(f'{label}:{index}: {name}.md "{cited}" — {why}')
    return problems


def main(argv: list[str]) -> int:
    """Refuse a quoted citation resolving to no heading, and any positional round/step citation."""
    docs = doc_set()
    if not docs:
        print("check_doc_refs: no markdown found", file=sys.stderr)
        return 1
    problems = []
    for arg in argv:
        path = Path(arg)
        if path.is_file() and path.resolve() != Path(__file__).resolve():
            problems.extend(check(path, docs))
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"\n{len(problems)} broken doc citation(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
