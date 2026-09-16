#!/usr/bin/env python3
"""The snapshot CSVs, printed side by side on one axis.

Every column is a proxy for adoption. Unique cloners sits closest to people;
PyPI downloads with mirrors excluded still counts every CI job; dependents sees
public manifests alone. They stay in separate columns for that reason.
"""

from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

DATA_DIR = Path(os.environ.get("TRIVIAJUDGE_METRICS_DIR", Path.home() / ".local/share/triviajudge-metrics"))
WINDOW = 30


def read(name: str) -> list[dict[str, str]]:
    """The rows of DATA_DIR/name, empty when the snapshot has never run."""
    path = DATA_DIR / name
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def number(value: str | None) -> int:
    """A CSV cell as an integer, treating a blank cell as zero."""
    return int(value) if value else 0


def main() -> int:
    """Print the window, the daily table, and the totals that can be totalled."""
    if not DATA_DIR.exists():
        print(f"no data at {DATA_DIR}; run snapshot.py first", file=sys.stderr)
        return 1

    cutoff = (datetime.now(UTC).date() - timedelta(days=WINDOW)).isoformat()

    traffic = [row for row in read("github_traffic.csv") if row["date"] >= cutoff]
    pypi: defaultdict[str, int] = defaultdict(int)
    for row in read("pypi_daily.csv"):
        if row["date"] >= cutoff and row["category"] == "without_mirrors":
            pypi[row["date"]] += number(row["downloads"])

    print(f"window: last {WINDOW} days, from {cutoff}\n")
    print(f"{'date':<12}{'cloners':>9}{'visitors':>10}{'pypi':>8}")
    by_day = {row["date"]: row for row in traffic}
    for day in sorted(set(by_day) | set(pypi)):
        row = by_day.get(day, {})
        print(
            f"{day:<12}{number(row.get('unique_cloners')):>9}"
            f"{number(row.get('unique_visitors')):>10}{pypi.get(day, 0):>8}"
        )

    # Unique cloners cannot be added across days: the same person recurs, once
    # per day they cloned. The peak day is the honest single number.
    peak = max((number(row["unique_cloners"]) for row in traffic), default=0)
    print(f"\npeak daily unique cloners: {peak} (days do not add up; the same person recurs)")
    print(f"pypi downloads, mirrors excluded: {sum(pypi.values())}")

    dependents_rows = read("dependents.csv")
    if dependents_rows:
        latest = dependents_rows[-1]
        print(f"dependent repositories: {latest['repositories']} (as of {latest['snapshot_date']})")

    releases = read("releases.csv")
    if releases:
        stamp = releases[-1]["snapshot_date"]
        total = sum(number(row["download_count"]) for row in releases if row["snapshot_date"] == stamp)
        print(f"release asset downloads: {total} (cumulative, as of {stamp})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
