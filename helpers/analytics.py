# analytics.py
"""
Analytics helpers for the admin console.

Metrics provided
----------------
* **New-customer percentage** – share of pickup requests coming from an
  address that has **never** appeared before.
* **Average first-return gap** – average number of days between the **first**
  and **second** request for every address that actually does come back.

For each metric we expose two keys:
* ``*_window`` – limited to the admin-selected date range
* ``*_all``    – calculated across the entire table

Design notes
------------
We deliberately pull only the two light columns (`address`, `date_filed`) into
Python and do the heavy logic there – casting string timestamps inside SQLite
proved too unpredictable.

Everything runs in milliseconds for <100 k rows, but when your table grows
larger consider:
* an index on `(address, date_filed)`
* a `first_seen DATE` column filled by a trigger
* nightly roll-ups cached in a summary table
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Tuple
from collections import Counter

from models import db, PickupRequest


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _pct(part: int, whole: int) -> float:
    """Return percentage rounded to 2 dp; 0 when ``whole`` is zero."""
    return round(part / whole * 100, 2) if whole else 0.0


def _parse_iso(date_str: str | None) -> date | None:
    """Parse YYYY-MM-DD[...] strings into ``date`` objects; ignore bad rows."""
    if not date_str or len(date_str) < 10:
        return None
    try:
        return date.fromisoformat(date_str[:10])
    except ValueError:
        return None

# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def new_customer_percentages(start_date: date, end_date: date) -> Dict[str, float]:
    """Return ``{"percent_window": x, "percent_all": y}``.

    The numerator counts **first-ever** requests for each unique address.
    The denominator is the number of requests (not addresses) in scope.
    """
    sess = db.session

    rows: List[tuple[str, str]] = (
        sess.query(PickupRequest.address, PickupRequest.date_filed)
        .filter(PickupRequest.date_filed.isnot(None))
        .all()
    )

    if not rows:
        return {"percent_window": 0.0, "percent_all": 0.0}

    earliest: Dict[str, date] = {}
    total_requests_window = 0

    for addr, datestr in rows:
        d = _parse_iso(datestr)
        if addr is None or d is None:
            continue

        if start_date <= d <= end_date:
            total_requests_window += 1

        if addr not in earliest or d < earliest[addr]:
            earliest[addr] = d

    firsts_in_window = sum(
        1 for first_seen in earliest.values() if start_date <= first_seen <= end_date
    )

    firsts_all_time = len(earliest)
    total_all = sum(1 for _, datestr in rows if _parse_iso(datestr) is not None)

    return {
        "percent_window": _pct(firsts_in_window, total_requests_window),
        "percent_all": _pct(firsts_all_time, total_all),
    }


def returning_customer_average_days(
    start_date: date, end_date: date
) -> Dict[str, Optional[float]]:
    """Average gap between first and second request **per returning address**.

    Addresses with only one request are ignored.
    """
    sess = db.session

    rows: List[tuple[str, str]] = (
        sess.query(PickupRequest.address, PickupRequest.date_filed)
        .filter(PickupRequest.date_filed.isnot(None))
        .order_by(PickupRequest.address, PickupRequest.date_filed)
        .all()
    )

    dates_by_addr: Dict[str, List[date]] = {}
    for addr, datestr in rows:
        d = _parse_iso(datestr)
        if addr is None or d is None:
            continue
        dates_by_addr.setdefault(addr, []).append(d)

    gaps_all: List[int] = []
    gaps_window: List[int] = []

    for dlist in dates_by_addr.values():
        if len(dlist) < 2:
            continue
        dlist.sort()
        gap_first = (dlist[1] - dlist[0]).days
        gaps_all.append(gap_first)
        if start_date <= dlist[1] <= end_date:
            gaps_window.append(gap_first)

    def _avg(lst: List[int]) -> Optional[float]:
        return round(sum(lst) / len(lst), 1) if lst else None

    return {
        "avg_window_days": _avg(gaps_window),
        "avg_all_days": _avg(gaps_all),
    }


def get_admin_metrics(start_date: date, end_date: date) -> Dict[str, float | None]:
    """Convenience wrapper for the Flask view."""
    metrics: Dict[str, float | None] = {}
    metrics.update(new_customer_percentages(start_date, end_date))
    metrics.update(returning_customer_average_days(start_date, end_date))
    return metrics

def _categorical_distribution(
    *,
    column,                        # SQLAlchemy column obj (PickupRequest.city …)
    start_date: date,
    end_date: date,
) -> Dict[str, list]:
    """Return dict ⇒ {categories, counts_all, percents_all, counts_window, …}."""
    sess = db.session
    rows: List[Tuple[str, str]] = (
        sess.query(column, PickupRequest.date_filed)
        .filter(PickupRequest.date_filed.isnot(None))
        .all()
    )

    if not rows:
        empty = {k: [] for k in (
            "categories",
            "counts_all",
            "percents_all",
            "counts_window",
            "percents_window",
        )}
        return empty

    counter_all: Counter[str] = Counter()
    counter_window: Counter[str] = Counter()

    for cat, datestr in rows:
        if cat is None:
            continue
        counter_all[cat] += 1
        d = _parse_iso(datestr)
        if d and start_date <= d <= end_date:
            counter_window[cat] += 1

    categories = [c for c, _ in counter_all.most_common()]

    total_all = sum(counter_all.values()) or 1
    total_window = sum(counter_window.values()) or 1

    return {
        "categories": categories,
        "counts_all": [counter_all[c] for c in categories],
        "percents_all": [_pct(counter_all[c], total_all) for c in categories],
        "counts_window": [counter_window.get(c, 0) for c in categories],
        "percents_window": [_pct(counter_window.get(c, 0), total_window) for c in categories],
    }


# ──────────────────────────────────────────────────────────────────────────────
#  Public wrappers for specific columns
# ──────────────────────────────────────────────────────────────────────────────

def city_distribution(start_date: date, end_date: date) -> Dict[str, list]:
    return _categorical_distribution(
        column=PickupRequest.city,
        start_date=start_date,
        end_date=end_date,
    )


def awareness_distribution(start_date: date, end_date: date) -> Dict[str, list]:
    return _categorical_distribution(
        column=PickupRequest.awareness,
        start_date=start_date,
        end_date=end_date,
    )
