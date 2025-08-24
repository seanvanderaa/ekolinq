from __future__ import annotations

from dataclasses import dataclass
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


# Robust import detection (case/whitespace tolerant)
_IMPORT_TAG = "imported via import-backfill cli"

def _is_imported(notes: Optional[str]) -> bool:
    if not notes:
        return False
    return notes.strip().lower() == _IMPORT_TAG


@dataclass(frozen=True)
class _Rec:
    addr: str
    d: date
    is_import: bool


def _load_recs() -> List[_Rec]:
    """
    Pull minimal columns and normalize into typed records. Results are ordered
    by (address, date) so consecutive logic is easy.
    """
    sess = db.session
    rows: List[Tuple[str, str, Optional[str]]] = (
        sess.query(
            PickupRequest.address,
            PickupRequest.date_filed,
            PickupRequest.admin_notes,
        )
        .filter(PickupRequest.date_filed.isnot(None))
        .order_by(PickupRequest.address, PickupRequest.date_filed)
        .all()
    )

    out: List[_Rec] = []
    for addr, datestr, notes in rows:
        d = _parse_iso(datestr)
        if not addr or d is None:
            continue
        out.append(_Rec(addr=addr, d=d, is_import=_is_imported(notes)))
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def new_customer_percentages(start_date: date, end_date: date) -> Dict[str, float]:
    """
    Return {"percent_window": x, "percent_all": y}.

    *Only* “real” requests (rows whose `admin_notes` do NOT equal the import tag)
    count toward denominators. Imported rows are used ONLY to establish whether
    an address existed before the first real request (to disqualify it from “new”).
    """
    recs = _load_recs()
    if not recs:
        return {"percent_window": 0.0, "percent_all": 0.0}

    earliest_any: Dict[str, date] = {}
    first_real: Dict[str, date] = {}
    total_requests_window = 0
    total_requests_all = 0

    for r in recs:
        # track earliest across ALL rows (imported or real)
        if r.addr not in earliest_any or r.d < earliest_any[r.addr]:
            earliest_any[r.addr] = r.d

        # only reals count as requests; also track first real
        if not r.is_import:
            total_requests_all += 1
            if start_date <= r.d <= end_date:
                total_requests_window += 1
            if r.addr not in first_real or r.d < first_real[r.addr]:
                first_real[r.addr] = r.d

    # numerators: addresses whose first REAL is also earliest for that address
    first_real_all = sum(1 for a, fr in first_real.items() if earliest_any.get(a) == fr)
    first_real_in_window = sum(
        1
        for a, fr in first_real.items()
        if start_date <= fr <= end_date and earliest_any.get(a) == fr
    )

    return {
        "percent_window": _pct(first_real_in_window, total_requests_window),
        "percent_all": _pct(first_real_all, total_requests_all),
    }


def returning_customer_average_days(
    start_date: date, end_date: date
) -> Dict[str, Optional[float]]:
    """
    Average gap (in days) across ALL “return” gaps per address:

      • If there is at least one REAL request:
          – If any IMPORT exists at or before the first REAL, include
            one gap: (first_real - latest_import_≤_first_real).
          – Also include ALL consecutive REAL→REAL gaps: (r2 - r1), (r3 - r2), ...

      • Addresses with no REAL requests are skipped.

    Windowing rule:
      – A gap contributes to the windowed average when its RIGHT-HAND event
        falls within [start_date, end_date]. (That right-hand event is always
        a REAL request in this metric.)

    Imported rows after the first REAL are ignored for gap math.
    """
    recs = _load_recs()
    if not recs:
        return {"avg_window_days": None, "avg_all_days": None}

    # group by address
    real_by_addr: Dict[str, List[date]] = {}
    import_by_addr: Dict[str, List[date]] = {}
    for r in recs:
        if r.is_import:
            import_by_addr.setdefault(r.addr, []).append(r.d)
        else:
            real_by_addr.setdefault(r.addr, []).append(r.d)

    gaps_all: List[int] = []
    gaps_window: List[int] = []

    for addr, reals in real_by_addr.items():
        if len(reals) == 0:
            continue

        # imports that are ≤ first_real may add a single baseline gap
        first_real = reals[0]
        imports = import_by_addr.get(addr, [])
        if imports:
            imports_before = [d for d in imports if d <= first_real]
            if imports_before:
                baseline = max(imports_before)
                gap = (first_real - baseline).days
                if gap >= 0:
                    gaps_all.append(gap)
                    if start_date <= first_real <= end_date:
                        gaps_window.append(gap)

        # add ALL consecutive real→real gaps
        for prev, curr in zip(reals, reals[1:]):
            gap = (curr - prev).days
            if gap >= 0:
                gaps_all.append(gap)
                if start_date <= curr <= end_date:
                    gaps_window.append(gap)

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


# ──────────────────────────────────────────────────────────────────────────────
#  (Unchanged) categorical distributions (kept here for completeness)
# ──────────────────────────────────────────────────────────────────────────────

def _categorical_distribution(
    *,
    column,
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

    recs_by_addr: Dict[str, List[Tuple[date, str]]] = {}
    for addr, datestr, cat in rows:
        d = _parse_iso(datestr)
        if not addr or d is None:
            continue
        recs_by_addr.setdefault(addr, []).append((d, cat))

    latest_all: Dict[str, Tuple[date, str]] = {}
    latest_win: Dict[str, Tuple[date, str]] = {}
    for addr, recs in recs_by_addr.items():
        latest_all[addr] = max(recs, key=lambda pair: pair[0])
        in_window = [(d, cat) for d, cat in recs if start_date <= d <= end_date]
        if in_window:
            latest_win[addr] = max(in_window, key=lambda pair: pair[0])

    counter_all   = Counter(cat for _, cat in latest_all.values())
    counter_window = Counter(cat for _, cat in latest_win.values())

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
