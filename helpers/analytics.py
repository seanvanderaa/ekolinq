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
    """
    Return {"percent_window": x, "percent_all": y}.

    *Only* “real” requests (rows whose `admin_notes` do **not** equal
    "Imported via import-backfill CLI") count toward the denominators.
    Imported rows are used **only** to establish whether an address was
    already a customer before the window.

    Numerator = first-ever request(s) for each unique address **that has at
    least one real request**.
    Denominator = total number of real requests in scope.
    """
    sess = db.session

    rows: list[tuple[str, str, str | None]] = (
        sess.query(
            PickupRequest.address,
            PickupRequest.date_filed,
            PickupRequest.admin_notes,
        )
        .filter(PickupRequest.date_filed.isnot(None))
        .all()
    )

    if not rows:
        return {"percent_window": 0.0, "percent_all": 0.0}

    earliest: dict[str, date] = {}
    has_real: set[str] = set()
    total_requests_window = 0
    total_requests_all = 0

    for addr, datestr, notes in rows:
        d = _parse_iso(datestr)
        if addr is None or d is None:
            continue

        # track the earliest request (imported *or* real) for each address
        if addr not in earliest or d < earliest[addr]:
            earliest[addr] = d

        is_imported = notes == "Imported via import-backfill CLI"

        if not is_imported:            # only “real” rows count as requests
            total_requests_all += 1
            if start_date <= d <= end_date:
                total_requests_window += 1
            has_real.add(addr)

    # --- numerators --------------------------------------------------------
    firsts_in_window = sum(
        1
        for addr, first_seen in earliest.items()
        if addr in has_real and start_date <= first_seen <= end_date
    )
    firsts_all_time = len(has_real)    # every address with ≥1 real request

    return {
        "percent_window": _pct(firsts_in_window, total_requests_window),
        "percent_all":    _pct(firsts_all_time,  total_requests_all),
    }


def returning_customer_average_days(
    start_date: date, end_date: date
) -> Dict[str, Optional[float]]:
    """
    Average gap (in days) between a location’s first and second request.

    Rules
    -----
    • Requests whose `admin_notes` contain *exactly*
      'Imported via import-backfill CLI' are ignored **unless** the same
      address also has at least one non-import request.
    • If both imported **and** real requests exist, we calculate the gap
      between the imported request that is closest (<=) to the first real
      request and that first real request.
    • If no imported requests exist, we calculate the gap between the first
      and second real requests, as before.
    • Addresses with fewer than two qualifying requests are skipped.
    """
    sess = db.session

    # Pull address, date, and admin_notes in one query, ordered for easier grouping
    rows: list[tuple[str, str, str | None]] = (
        sess.query(
            PickupRequest.address,
            PickupRequest.date_filed,
            PickupRequest.admin_notes,
        )
        .filter(PickupRequest.date_filed.isnot(None))
        .order_by(PickupRequest.address, PickupRequest.date_filed)
        .all()
    )

    # Group by address: list of (date, is_imported) tuples
    recs_by_addr: dict[str, list[tuple[date, bool]]] = {}
    for addr, datestr, notes in rows:
        d = _parse_iso(datestr)
        if addr is None or d is None:
            continue
        is_import = notes == "Imported via import-backfill CLI"
        recs_by_addr.setdefault(addr, []).append((d, is_import))

    gaps_all: list[int] = []
    gaps_window: list[int] = []

    for recs in recs_by_addr.values():
        # split into imported / real lists, each already in chronological order
        imported = [d for d, imp in recs if imp]
        real     = [d for d, imp in recs if not imp]

        # ---- choose the two dates that define the gap ----
        first, second = None, None

        if real:
            if imported:
                # use the imported date closest *before* the first real date
                first_real = real[0]
                first_import = max(
                    (d for d in imported if d <= first_real),
                    default=imported[0],           # none precede → earliest import
                )
                first, second = first_import, first_real
            elif len(real) >= 2:
                first, second = real[0], real[1]
        # else: only imported requests → ignore

        if first and second:
            gap_days = (second - first).days
            gaps_all.append(gap_days)
            if start_date <= second <= end_date:
                gaps_window.append(gap_days)

    def _avg(lst: list[int]) -> Optional[float]:
        return round(sum(lst) / len(lst), 1) if lst else None

    return {
        "avg_window_days": _avg(gaps_window),
        "avg_all_days":    _avg(gaps_all),
    }


def get_admin_metrics(start_date: date, end_date: date) -> Dict[str, float | None]:
    """Convenience wrapper for the Flask view."""
    metrics: Dict[str, float | None] = {}
    metrics.update(new_customer_percentages(start_date, end_date))
    metrics.update(returning_customer_average_days(start_date, end_date))
    return metrics

def _categorical_distribution(
    *,
    column,                        # SQLAlchemy column obj (PickupRequest.city, PickupRequest.awareness, …)
    start_date: date,
    end_date: date,
) -> Dict[str, list]:
    """
    Return dict ⇒ {categories, counts_all, percents_all, counts_window, percents_window},
    counting each unique address only once:

      - overall (“*_all”): each address’s latest-ever value
      - window (“*_window”): each address’s latest value within [start_date, end_date]

    Rows with column == None, empty, or "Unknown" are skipped.
    """
    sess = db.session

    # 1) pull address, date_filed, and the chosen category column
    rows: List[Tuple[str, str, str]] = (
        sess.query(
            PickupRequest.address,
            PickupRequest.date_filed,
            column,
        )
        .filter(
            PickupRequest.address.isnot(None),
            column.isnot(None),
            column != "",
            column != "Unknown",
        )
        .all()
    )

    # 2) group by address
    recs_by_addr: Dict[str, List[Tuple[date, str]]] = {}
    for addr, datestr, cat in rows:
        d = _parse_iso(datestr)
        if not addr or d is None:
            continue
        recs_by_addr.setdefault(addr, []).append((d, cat))

    # 3) for each address pick:
    #    - latest overall
    #    - latest within window (if any)
    latest_all: Dict[str, Tuple[date, str]] = {}
    latest_win: Dict[str, Tuple[date, str]] = {}
    for addr, recs in recs_by_addr.items():
        # overall latest
        latest_all[addr] = max(recs, key=lambda pair: pair[0])
        # window-limited latest
        in_window = [(d, cat) for d, cat in recs if start_date <= d <= end_date]
        if in_window:
            latest_win[addr] = max(in_window, key=lambda pair: pair[0])

    # 4) tally counts
    counter_all   = Counter(cat for _, cat in latest_all.values())
    counter_window = Counter(cat for _, cat in latest_win.values())

    # 5) build final lists in most-common order (by all-time)
    categories    = [c for c, _ in counter_all.most_common()]
    total_all     = sum(counter_all.values()) or 1
    total_window  = sum(counter_window.values()) or 1

    return {
        "categories":      categories,
        "counts_all":      [counter_all[c]       for c in categories],
        "percents_all":    [_pct(counter_all[c],      total_all)   for c in categories],
        "counts_window":   [counter_window.get(c, 0) for c in categories],
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



