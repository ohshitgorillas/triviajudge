"""The markdown gate's pattern screen: the mechanical half of "what happened, not what holds".

A regex answers a handful of the shapes the model judge otherwise has to rule
on every time: a dated event, a number marking a position in history, a
struck-through or closed-out item, a correction that narrates the mistake it
fixes, narration by negation, a completed-run record, past behavior, and a
line that addresses the judge directly.
What this module refuses never reaches the judge; what it leaves is what the
judge reads.

A blockquote line (``> ...``) quotes a source and skips the screen entirely,
as does a line indented four or more spaces or by a tab, the same reading an
indented code block or a list continuation gets. An inline code span is
stripped before a pattern is tried against the line, as
``triviajudge.changelog_screen`` strips one for its word count, so a family
word sitting only inside a span does not trip its pattern.

``history-ok: <reason>`` exempts a line from both the screen and the judge,
the same pragma and the same contract ``triviajudge.archaeology`` and
``triviajudge.comment_trivia.screen`` use; a bare ``history-ok:`` with no
reason after it is refused.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from triviajudge.archaeology import BARE_PRAGMA, EXEMPT, PRAGMA

if TYPE_CHECKING:
    from triviajudge.core import Line

#: An inline code span; stripped to a single space before a pattern is tried, so a
#: family word quoted as code cannot trip the screen.
CODE_RE = re.compile(r"`[^`]*`")

#: A blockquote line, whatever it indents by; it quotes a source and is never screened.
BLOCKQUOTE = re.compile(r"^\s*>")

#: A line indented four or more spaces, or by a tab: an indented code block or a list
#: continuation, read the way ``prose_only`` already reads such lines elsewhere.
INDENTED = re.compile(r"^(?: {4,}|\t)")

#: An ISO date, the same shape ``archaeology.PATTERNS`` looks for in a comment.
_DATE = r"[0-9]{4}-[01][0-9]-[0-3][0-9]"

#: The event verbs a dated line names, whole word, case-insensitive.
_VERB = (
    r"verified|approved|decided|collected|benchmarked|re-checked|reviewed|"
    r"filed|captured|measured|passed|failed|pass|fail|done"
)

#: The gap between a verb and a date that still reads as one claim: at most 40
#: characters, none of them a ``.`` or a ``|`` — a table row's cell boundary or a
#: sentence end, either of which means the two are not the same remark.
_GAP = r"[^.|]{0,40}"

#: A past-tense verb: ``was``, ``were``, ``had``, or a regular ``-ed`` form that is
#: not a present passive after ``is``, ``are``, ``be``, ``been`` or ``not``, nor an
#: adjective after ``a``, ``an`` or ``the`` ("a named repair"). The
#: ``-eed`` words (``need``, ``speed``) are not past tense and are left out.
_PAST = (
    r"\b(?:was|were|had|(?<!\bis )(?<!\bare )(?<!\bbe )(?<!\bbeen )(?<!\bnot )(?<!\ba )(?<!\ban )(?<!\bthe )"
    r"\w{2,}(?<!e)ed)\b"
)

#: A round or phase number is history only when a past-tense verb follows it in
#: the same clause: "round 2 was collected" narrates a run, "round 1 lists every
#: question" is a rule for every run. The clause ends at ``.``, ``;``, ``:`` or ``|``.
_POSITION = re.compile(
    rf"\b(?:round[\s-]|phase\s+)\d+\b[^.;:|]{{0,40}}?{_PAST}", re.IGNORECASE
)

#: Past behavior, not the passive voice of a present-tense verb phrase: the
#: auxiliaries it follows are excluded, each by its own fixed-width lookbehind,
#: since a variable-width one is not allowed.
_USED_TO = re.compile(
    r"(?<!\bbe )(?<!\bis )(?<!\bare )(?<!\bwas )(?<!\bwere )(?<!\bbeen )"
    r"\bused to\b",
    re.IGNORECASE,
)

#: ``(pattern, label)``, same shape as ``triviajudge.archaeology.PATTERNS``. Every
#: pattern is case-insensitive; each is tried against the line with its inline code
#: spans already stripped.
PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            rf"\b(?:{_VERB})\b{_GAP}\b{_DATE}\b|\b{_DATE}\b{_GAP}\b(?:{_VERB})\b",
            re.IGNORECASE,
        ),
        "dated event",
    ),
    (_POSITION, "position in history"),
    (
        re.compile(r"\bstep-\d+\s+hand-back\b", re.IGNORECASE),
        "position in history",
    ),
    (
        re.compile(r"\bhand-back\s+(?:pass|fail)\b", re.IGNORECASE),
        "position in history",
    ),
    (re.compile(r"~~.+?~~"), "resolved item"),
    (re.compile(r"^\s*resolved:", re.IGNORECASE), "resolved item"),
    (re.compile(r"^\s*still open:", re.IGNORECASE), "resolved item"),
    (
        re.compile(
            r"\b(?:previously|formerly)\s+(?:documented|named|called|stated)\b",
            re.IGNORECASE,
        ),
        "correction narration",
    ),
    (re.compile(r"\bmade here earlier\b", re.IGNORECASE), "correction narration"),
    (re.compile(r"\bthen-current\b", re.IGNORECASE), "correction narration"),
    (re.compile(r"\bworks the same\b", re.IGNORECASE), "narration by negation"),
    (re.compile(r"\bsame as before\b", re.IGNORECASE), "narration by negation"),
    (re.compile(r"\bunchanged from\b", re.IGNORECASE), "narration by negation"),
    (re.compile(r"\brun completed\b", re.IGNORECASE), "process record"),
    (
        re.compile(
            r"\ball\s+\d+\s+\w+\s+(?:graded|passed|checked|done)\b", re.IGNORECASE
        ),
        "process record",
    ),
    (re.compile(r"\bran twice\b", re.IGNORECASE), "process record"),
    (_USED_TO, "past behavior"),
    (re.compile(r"\bnot trivia\b", re.IGNORECASE), "addressed to the judge"),
    (re.compile(r"\bkeep this line\b", re.IGNORECASE), "addressed to the judge"),
    (
        re.compile(r"\bpresent tense by design\b", re.IGNORECASE),
        "addressed to the judge",
    ),
)


def bypassed(text: str) -> bool:
    """Whether a line skips the screen outright: a blockquote, or a line the judge reads as code."""
    return bool(BLOCKQUOTE.match(text) or INDENTED.match(text))


def refused(line: Line) -> list[str]:
    """Return one complaint per pattern hit, or one for a reasonless pragma; empty when exempt."""
    text = CODE_RE.sub(" ", line.text)
    if BARE_PRAGMA.search(text):
        return [f"{line.id}: bare `{PRAGMA}` needs a reason"]
    if EXEMPT.search(text):
        return []
    return [
        f'{line.id}: {label} ("{found.group(0)}")'
        for pattern, label in PATTERNS
        if (found := pattern.search(text))
    ]


def screen(lines: list[Line]) -> tuple[list[Line], list[str]]:
    """Return the lines the judge should see, and one complaint per pattern hit or reasonless pragma."""
    keep: list[Line] = []
    complaints: list[str] = []
    for line in lines:
        if bypassed(line.text):
            keep.append(line)
            continue
        found = refused(line)
        complaints.extend(found)
        if not found and not EXEMPT.search(CODE_RE.sub(" ", line.text)):
            keep.append(line)
    return keep, complaints
