#!/usr/bin/env python3
"""Snapshots of the adoption proxies for triviajudge, written outside the repo.

None of these sources reports users. Each one is a proxy carrying its own bias,
so the CSVs keep them apart rather than summing them into one wrong number:

  github_traffic.csv  unique cloners and visitors, the closest thing here to a
                      human count. GitHub keeps 14 days, so this file is only as
                      complete as the cadence that writes it.
  pypi_daily.csv      daily downloads, with and without mirrors. One CI matrix
                      can produce twenty of these for a single push.
  releases.csv        exact per-asset download counts, cumulative. Successive
                      snapshots supply the history the API omits.
  dependents.csv      repositories declaring triviajudge in a manifest, and the
                      only scraped number, so the first to break on a restyle.

Rows are keyed by date and rewritten in place, so a second run in one day is
harmless. One source failing leaves the other three intact.
"""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, cast

REPO = "ohshitgorillas/triviajudge"
PACKAGE = "triviajudge"
DATA_DIR = Path(os.environ.get("TRIVIAJUDGE_METRICS_DIR", Path.home() / ".local/share/triviajudge-metrics"))
USER_AGENT = f"triviajudge-metrics (+https://github.com/{REPO})"
# Resolved once, at import, so the timer spawns the same gh a shell would.
GH = shutil.which("gh")
TIMEOUT = 30

Row = dict[str, Any]

#: What one `gh api` or pypistats call answers with: a JSON object, or an array of them.
JsonObject = dict[str, Any]
JsonArray = list[JsonObject]


def today() -> str:
    """The current UTC date, in the ISO form the CSVs key on."""
    return datetime.now(UTC).date().isoformat()


def warn(message: str) -> None:
    """A note on stderr that one source came back empty or broken."""
    print(f"warn: {message}", file=sys.stderr)


def _open(url: str) -> IO[bytes]:
    """The response for an https URL built from this module's constants."""
    if not url.startswith("https://"):
        raise ValueError(f"refusing a non-https URL: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return cast("IO[bytes]", urllib.request.urlopen(request, timeout=TIMEOUT))


def fetch_json(url: str) -> JsonObject:
    """The decoded JSON body at url."""
    with _open(url) as response:
        return cast("JsonObject", json.load(response))


def fetch_text(url: str) -> str:
    """The body at url as text, with undecodable bytes replaced."""
    with _open(url) as response:
        body: bytes = response.read()
    return body.decode("utf-8", "replace")


def gh_api(path: str) -> JsonObject | JsonArray:
    """The decoded JSON body of a `gh api` call, which carries the stored token."""
    if GH is None:
        raise RuntimeError("gh is not on PATH")
    result = subprocess.run(
        [GH, "api", path],
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "gh api failed"
        raise RuntimeError(detail)
    return cast("JsonObject | JsonArray", json.loads(result.stdout))


def upsert(name: str, fields: list[str], rows: list[Row], key: tuple[str, ...]) -> None:
    """Merge rows into DATA_DIR/name, replacing any row carrying the same key."""
    path = DATA_DIR / name
    merged: dict[tuple[str, ...], Row] = {}
    if path.exists():
        with path.open(newline="") as handle:
            for existing in csv.DictReader(handle):
                merged[tuple(existing[column] for column in key)] = dict(existing)
    for row in rows:
        merged[tuple(str(row[column]) for column in key)] = row
    ordered = sorted(merged.values(), key=lambda row: tuple(str(row[column]) for column in key))
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(ordered)
    print(f"{name}: {len(rows)} row(s) written, {len(ordered)} total")


def github_traffic() -> None:
    """Fourteen days of clone and view counts, one row per day."""
    by_day: dict[str, Row] = {}
    for kind in ("clones", "views"):
        payload = cast("JsonObject", gh_api(f"repos/{REPO}/traffic/{kind}"))
        for entry in payload.get(kind, []):
            day = entry["timestamp"][:10]
            row = by_day.setdefault(
                day,
                {"date": day, "clones": 0, "unique_cloners": 0, "views": 0, "unique_visitors": 0},
            )
            if kind == "clones":
                row["clones"] = entry["count"]
                row["unique_cloners"] = entry["uniques"]
            else:
                row["views"] = entry["count"]
                row["unique_visitors"] = entry["uniques"]

    upsert(
        "github_traffic.csv",
        ["date", "clones", "unique_cloners", "views", "unique_visitors"],
        list(by_day.values()),
        ("date",),
    )


def pypi_daily() -> None:
    """Daily download counts from pypistats, mirrors held in their own rows."""
    payload = fetch_json(f"https://pypistats.org/api/packages/{PACKAGE}/overall")
    rows: list[Row] = [
        {"date": entry["date"], "category": entry["category"], "downloads": entry["downloads"]}
        for entry in payload.get("data", [])
    ]
    upsert("pypi_daily.csv", ["date", "category", "downloads"], rows, ("date", "category"))


def releases() -> None:
    """Cumulative download counts for every asset attached to a release."""
    payload = cast("JsonArray", gh_api(f"repos/{REPO}/releases?per_page=100"))
    stamp = today()
    rows: list[Row] = [
        {
            "snapshot_date": stamp,
            "tag": release["tag_name"],
            "asset": asset["name"],
            "download_count": asset["download_count"],
        }
        for release in payload
        for asset in release.get("assets", [])
    ]
    if not rows:
        # A source-only project attaches no assets, and recording the zero keeps
        # that state distinguishable from a fetch that failed.
        rows = [{"snapshot_date": stamp, "tag": "(none)", "asset": "(no assets)", "download_count": 0}]
    upsert(
        "releases.csv",
        ["snapshot_date", "tag", "asset", "download_count"],
        rows,
        ("snapshot_date", "tag", "asset"),
    )


def dependents() -> None:
    """The dependents counts, scraped from the network page GitHub renders."""
    html = fetch_text(f"https://github.com/{REPO}/network/dependents")
    counts: dict[str, int | str] = {}
    for label in ("Repositories", "Packages"):
        match = re.search(r"([\d,]+)\s*\n?\s*" + label, html)
        counts[label.lower()] = int(match.group(1).replace(",", "")) if match else ""
    if counts["repositories"] == "":
        warn("dependents: repository count not found; GitHub markup likely changed")
    upsert(
        "dependents.csv",
        ["snapshot_date", "repositories", "packages"],
        [
            {
                "snapshot_date": today(),
                "repositories": counts["repositories"],
                "packages": counts["packages"],
            }
        ],
        ("snapshot_date",),
    )


SOURCES = (
    ("github_traffic", github_traffic),
    ("pypi_daily", pypi_daily),
    ("releases", releases),
    ("dependents", dependents),
)


def main() -> int:
    """Collect every source, reporting how many survived."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"{datetime.now(UTC).isoformat(timespec='seconds')} -> {DATA_DIR}")
    failures = []
    for name, source in SOURCES:
        try:
            source()
        except urllib.error.HTTPError as error:
            # pypistats answers 429 under load. A missed day is a gap in one
            # series, and the remaining three still collect.
            warn(f"{name}: HTTP {error.code}")
            failures.append(name)
        except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError) as error:
            warn(f"{name}: {error}")
            failures.append(name)
    if failures:
        print(f"failed: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
