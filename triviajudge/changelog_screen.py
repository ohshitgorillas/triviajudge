"""The changelog gate's pattern screen: the mechanical half of a release note's shape.

One bullet is one logical line, at most ``WORD_CAP`` words, opening with a bold
lead, impersonal, free of marketing register and of narration by negation, under
one heading per kind in Keep a Changelog order. A bullet the screen refuses is
already refused, so the judge in ``triviajudge.changelog_trivia`` reads only
what this module leaves.

A candidate is one bullet under ``## [Unreleased]``, its continuation lines
joined. Released sections are history and are never rewritten, so the reader
stops at the next ``## `` heading.
"""

from __future__ import annotations

import re

from triviajudge.core import Line

#: The one file the changelog gate reads, repo-relative. A changelog under another
#: name is a changelog the gate does not judge.
CHANGELOG = "CHANGELOG.md"

#: The section the screen reads. Everything below it has shipped.
UNRELEASED = "## [Unreleased]"

#: Words per bullet. Enough for cause and fix in one line; not enough for the
#: fix's autobiography.
WORD_CAP = 75

#: Keep a Changelog's order, plus the ``Internal`` bucket for changes with no
#: user-visible face.
ORDER = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security", "Internal")

SECOND_PERSON = re.compile(
    r"\b(you|your|yours|yourself|you're|you've|you'd|you'll)\b", re.IGNORECASE
)

#: Register, not vocabulary: each of these reaches for the reader's feelings
#: about the change instead of stating it. ``finally`` and ``quietly`` are here
#: because they editorialize a fix that the sentence beside them already states.
HYPE = (
    "simply",
    "seamless",
    "seamlessly",
    "powerful",
    "robust",
    "delightful",
    "dramatically",
    "significantly",
    "blazing",
    "finally",
    "quietly",
    "magic",
    "just works",
    "under the hood",
    "where they belong",
    "out of the box",
)

#: Narration by negation: a clause whose content is that something did *not*
#: change. It reads as reassurance and carries nothing — a changelog says what
#: changed, and a reader assumes everything it does not mention stayed put. Where
#: the clause is load-bearing it is a scope boundary, and a scope boundary states
#: positively which things the change reached: "only chainless profiles are
#: filled in", not "profiles that already carry a chain are untouched".
NEGATION = (
    "is unchanged",
    "are unchanged",
    "remains unchanged",
    "remain unchanged",
    "stays unchanged",
    "otherwise unchanged",
    "unaffected",
    "untouched",
    "nothing changed",
    "nothing else changes",
    "nothing else is affected",
    "everything else is unchanged",
    "everything else works as before",
    "no other settings",
)

VERSION_RE = re.compile(r"^## ")
HEADING_RE = re.compile(r"^### (.+?)\s*$")
BULLET_RE = re.compile(r"^- ")
CODE_RE = re.compile(r"`[^`]*`")
MARKUP_RE = re.compile(r"[*_]")

#: One bullet, its kind, and its lines: what the section reader hands the rest of the module.
Entry = tuple[int, str, list[str]]


def section(text: str) -> list[tuple[int, str]]:
    """(line number, text) for the ``[Unreleased]`` section's body, 1-indexed."""
    body: list[tuple[int, str]] = []
    inside = False
    for number, line in enumerate(text.splitlines(), start=1):
        if line.startswith(UNRELEASED):
            inside = True
            continue
        if inside and VERSION_RE.match(line):
            break
        if inside:
            body.append((number, line))
    return body


def bullets(body: list[tuple[int, str]]) -> list[Entry]:
    """(line number, kind, lines) for every bullet in the section, continuation lines included."""
    found: list[Entry] = []
    kind = ""
    for number, line in body:
        if match := HEADING_RE.match(line):
            kind = match.group(1)
        elif BULLET_RE.match(line):
            found.append((number, kind, [line]))
        elif found and line.strip() and line.startswith((" ", "\t")):
            found[-1][2].append(line)
    return found


def headings(body: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """(line number, kind) for every ``###`` heading in the section."""
    return [
        (number, match.group(1))
        for number, line in body
        if (match := HEADING_RE.match(line))
    ]


def joined(block: list[str]) -> str:
    """One bullet's lines as the single line it is meant to be."""
    return " ".join(line.strip() for line in block)


def words(text: str) -> int:
    """Word count of a bullet.

    Code spans and emphasis markers are dropped, and so is any token carrying no
    letter or digit: a dash standing between two clauses is punctuation the
    author chose over a comma, and pricing it as a word taxes the punctuation
    rather than the prose.
    """
    stripped = MARKUP_RE.sub("", CODE_RE.sub(" ", text))
    return sum(1 for token in stripped.split() if any(char.isalnum() for char in token))


def entry_faults(number: int, block: list[str]) -> list[str]:
    """Every screen rule this one bullet breaks."""
    text = joined(block)
    found = []
    if len(block) > 1:
        found.append(
            f"{CHANGELOG}:{number}: entry runs to a second paragraph — one entry, one line"
        )
    if (count := words(text)) > WORD_CAP:
        found.append(f"{CHANGELOG}:{number}: entry is {count} words, cap is {WORD_CAP}")
    if not text.startswith("- **"):
        found.append(
            f"{CHANGELOG}:{number}: entry does not open with a bold lead (`- **…**`)"
        )
    if match := SECOND_PERSON.search(text):
        found.append(
            f"{CHANGELOG}:{number}: second person {match.group(0)!r} — write it impersonally"
        )
    lowered = text.lower()
    found.extend(
        f"{CHANGELOG}:{number}: {word!r} is marketing register — state the change"
        for word in HYPE
        if re.search(rf"\b{re.escape(word)}\b", lowered)
    )
    found.extend(
        f"{CHANGELOG}:{number}: {phrase!r} narrates by negation — cut it, or state the scope positively"
        for phrase in NEGATION
        if re.search(rf"\b{re.escape(phrase)}\b", lowered)
    )
    return found


def heading_faults(found: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """(line number, complaint) for every duplicate, unknown or out-of-order heading."""
    problems: list[tuple[int, str]] = []
    seen: set[str] = set()
    rank = -1
    for number, kind in found:
        if kind in seen:
            problems.append(
                (
                    number,
                    f"{CHANGELOG}:{number}: second '### {kind}' — one heading per kind, merged",
                )
            )
        seen.add(kind)
        if kind not in ORDER:
            problems.append(
                (
                    number,
                    f"{CHANGELOG}:{number}: unknown section '{kind}' — one of {list(ORDER)}",
                )
            )
            continue
        if (position := ORDER.index(kind)) < rank:
            problems.append(
                (
                    number,
                    f"{CHANGELOG}:{number}: '### {kind}' is out of order — {list(ORDER)}",
                )
            )
        rank = max(rank, position)
    return problems


def touched(number: int, block: list[str], added: set[int]) -> bool:
    """Whether a change added any line of this bullet."""
    return bool(added & set(range(number, number + len(block))))


def screen(text: str, added: set[int]) -> tuple[list[Line], list[str]]:
    """The added bullets the judge should read, and one complaint per rule the added text breaks."""
    body = section(text)
    complaints = [
        problem for number, problem in heading_faults(headings(body)) if number in added
    ]
    keep: list[Line] = []
    for number, _kind, block in bullets(body):
        if not touched(number, block, added):
            continue
        faults = entry_faults(number, block)
        complaints.extend(faults)
        if not faults:
            keep.append(Line(CHANGELOG, number, joined(block)))
    return keep, complaints


def whole_section(text: str) -> tuple[list[Line], list[str]]:
    """Every bullet under ``[Unreleased]`` carrying its kind, and every complaint the screen raises."""
    body = section(text)
    complaints = [problem for _number, problem in heading_faults(headings(body))]
    lines: list[Line] = []
    for number, kind, block in bullets(body):
        complaints.extend(entry_faults(number, block))
        lines.append(Line(CHANGELOG, number, f"({kind}) {joined(block)}"))
    return lines, complaints


def screen_records(cands: list[Line]) -> tuple[list[Line], list[str]]:
    """Calibration records through the same screen: each record is one bullet already."""
    keep: list[Line] = []
    complaints: list[str] = []
    for cand in cands:
        faults = entry_faults(cand.number, [cand.text])
        complaints.extend(faults)
        if not faults:
            keep.append(cand)
    return keep, complaints
