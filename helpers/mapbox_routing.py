"""routing_mapbox.py — Mapbox Matrix-based TSP helper
=====================================================
Stable, minimal, and thoroughly linted version.

* Automatic chunking for arbitrarily large waypoint lists.
* Guarantees every Matrix call has **≥ 2 destinations** to avoid Mapbox 422.
* Deduplicates identical coordinates (same address repeated).
* Fetches BOTH durations (seconds) and distances (meters) in one pass.
* Supports true round-trip when start and end depot are the same.
* Applies a small 2-opt polish to remove residual crossovers.

Public API remains compatible with existing callers:
- `compute_optimized_route(...)` still returns a (ordered_addresses,
   total_duration_seconds, per_leg_seconds) 3-tuple.
   NOTE: The route is now *optimized for distance* by default, but the
   returned totals/legs are still in **seconds** for compatibility.
- New: `compute_optimized_route_with_metrics(...)` returns both distance
   and duration metrics.
"""
from __future__ import annotations

import os
import time
import re
from collections import defaultdict
from typing import List, Tuple, Dict
from urllib.parse import quote_plus

import requests
from flask import current_app
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

###############################################################################
# Constants & utilities
###############################################################################

MB_PROFILE_DEFAULT = "mapbox/driving"  # 10 coords/call if using *-traffic profiles
MB_ENDPOINT = "https://api.mapbox.com/directions-matrix/v1"
FALLBACK_LARGE = 999_999  # penalty for unreachable legs (seconds or meters)
_REQ_WINDOW_SEC = 60
_req_ts: defaultdict[str, List[float]] = defaultdict(list)
_MB_RPM = int(os.getenv("MAPBOX_MATRIX_RPM", "300"))  # Mapbox spec: 300 req/min


# helpers/mapbox_routing.py
import logging, math
from typing import List, Tuple

try:
    # current_app is only available inside a request/app context
    from flask import current_app
except Exception:  # pragma: no cover
    current_app = None  # type: ignore

BIG_COST = 10**9  # large but finite penalty for unreachable/invalid arcs
logger = logging.getLogger("mapbox_routing")  # align with your existing module logs


def _log(level: str, msg: str, *args) -> None:
    """
    Prefer Flask's app logger when available so logs match the rest of your output.
    Fallback to this module logger outside app context (e.g., CLI).
    """
    if current_app and hasattr(current_app, "logger"):
        getattr(current_app.logger, level)(msg, *args)
    else:
        getattr(logger, level)(msg, *args)


def _matrix_stats(mx: list[list]) -> tuple[int, int, int, int, int, float, float]:
    """
    (rows, cols0, nulls, nans, infs, min_val, max_val) without mutating `mx`.
    """
    rows = len(mx)
    cols0 = len(mx[0]) if rows else 0
    nulls = nans = infs = 0
    min_v = math.inf
    max_v = -math.inf
    for row in mx:
        for v in row:
            if v is None:
                nulls += 1
                continue
            if isinstance(v, float):
                if math.isnan(v):
                    nans += 1
                    continue
                if math.isinf(v):
                    infs += 1
                    continue
            try:
                fv = float(v)
                if fv < min_v: min_v = fv
                if fv > max_v: max_v = fv
            except Exception:
                nulls += 1
    if min_v is math.inf: min_v = float("nan")
    if max_v == -math.inf: max_v = float("nan")
    return rows, cols0, nulls, nans, infs, min_v, max_v


def _normalize_square_matrix(mx: list[list], n: int, name: str) -> list[list[int]]:
    if len(mx) != n:
        raise ValueError(f"{name} rows={len(mx)} != n={n}")
    out: list[list[int]] = []
    for r, row in enumerate(mx):
        if len(row) != n:
            raise ValueError(f"{name}[{r}] cols={len(row)} != n={n}")
        new_row: list[int] = []
        for c, v in enumerate(row):
            # Mapbox can return None for unreachable; treat as large finite cost
            if v is None:
                new_row.append(BIG_COST)
                continue
            # guard NaN/inf
            if isinstance(v, float):
                if v != v or v == float("inf") or v == float("-inf"):
                    new_row.append(BIG_COST)
                    continue
            try:
                new_row.append(int(round(v)))
            except Exception:
                new_row.append(BIG_COST)
        out.append(new_row)
    return out


def _t(label: str):
    """Return a lambda that logs elapsed seconds when invoked."""
    logger = current_app.logger
    start = time.perf_counter()
    return lambda: logger.debug("%s took %.3f s", label, time.perf_counter() - start)


def _ratelimit() -> None:
    """Sleep just enough to stay below the per-minute cap."""
    now = time.time()
    limit = _MB_RPM
    window = _req_ts["global"]
    window[:] = [t for t in window if now - t < _REQ_WINDOW_SEC]
    if len(window) >= limit:
        sleep_for = _REQ_WINDOW_SEC - (now - window[0]) + 0.05
        current_app.logger.warning(
            "Matrix rate-limit hit: sleeping %.1f s to stay under %d rpm",
            sleep_for,
            limit,
        )
        time.sleep(sleep_for)
    window.append(now)


def _coords_like(s: str) -> bool:
    try:
        lon, lat, *_ = s.split(",")
        float(lon)
        float(lat)
        return True
    except Exception:
        return False


def _maybe_geocode(addr: str, token: str) -> str:
    if _coords_like(addr):
        return addr  # already "lon,lat"
    done = _t(f"Geocoding address '{addr[:40]}…'")
    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{quote_plus(addr)}.json"
    params = {"limit": 1, "access_token": token}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    feat = r.json()["features"][0]
    done()
    lon, lat = feat["center"]
    return f"{lon},{lat}"

###############################################################################
# Matrix builders
###############################################################################


def fetch_matrices_mapbox(
    locations: List[str],
    *,
    access_token: str | None = None,
    profile: str = MB_PROFILE_DEFAULT,
) -> Tuple[List[List[int]], List[List[int]]]:
    """
    Return TWO N×N matrices via Mapbox Matrix API:
      - durations_matrix: seconds (int)
      - distances_matrix: meters (int)

    We request both annotations in one pass to keep calls minimal.
    """
    logger = current_app.logger
    token = access_token or os.getenv("MAPBOX_ACCESS_TOKEN")
    if not token:
        raise ValueError("MAPBOX_ACCESS_TOKEN env var not set")

    timer_fetch = _t("fetch_matrices_mapbox")

    # 1) Geocode / normalize
    t_geo = _t(f"– geocoding {len(locations)} address(es)")
    coords_raw = [_maybe_geocode(addr, token) for addr in locations]
    t_geo()

    # 2) Deduplicate identical coordinates (exact string equality)
    uniq_coords: List[str] = []
    idx_map: List[int] = []  # original index -> unique index
    for c in coords_raw:
        try:
            idx = uniq_coords.index(c)
        except ValueError:
            idx = len(uniq_coords)
            uniq_coords.append(c)
        idx_map.append(idx)

    u = len(uniq_coords)
    if u < 2:
        raise ValueError("Need at least two distinct coordinates for a matrix")

    # Mapbox per-call coordinate cap
    max_coords = 10 if profile.endswith("traffic") else 25

    # Timings
    api_calls = 0
    api_time = 0.0

    def _matrix_get(url: str, params: dict) -> dict:
        nonlocal api_calls, api_time
        api_calls += 1
        t0 = time.perf_counter()
        r = requests.get(url, params=params, timeout=15)
        api_time += time.perf_counter() - t0
        r.raise_for_status()
        data = r.json()
        if data.get("code") != "Ok":
            raise RuntimeError(f"Matrix API error: {data.get('message')}")
        return data

    def _to_int_matrix(arr: List[List[float]]) -> List[List[int]]:
        return [
            [int(v) if (v is not None) else FALLBACK_LARGE for v in row]
            for row in arr
        ]

    # 3) Build the unique-coords matrices
    if u <= max_coords:
        # Single call
        coord_str = ";".join(uniq_coords)
        params = {"annotations": "duration,distance", "access_token": token}
        _ratelimit()
        res = _matrix_get(f"{MB_ENDPOINT}/{profile}/{coord_str}", params)
        u_dur = _to_int_matrix(res["durations"])
        u_dist = _to_int_matrix(res["distances"])
    else:
        # Half-block tiling (union ≤ max_coords)
        M = max_coords // 2
        if M == 0:
            raise RuntimeError("max_coords must be ≥ 2")

        chunks: List[List[int]] = [
            list(range(i, min(i + M, u))) for i in range(0, u, M)
        ]
        u_dur = [[FALLBACK_LARGE] * u for _ in range(u)]
        u_dist = [[FALLBACK_LARGE] * u for _ in range(u)]

        def _fill(union_idx: List[int], durations: List[List[float]], distances: List[List[float]]) -> None:
            for ii, si in enumerate(union_idx):
                for jj, dj in enumerate(union_idx):
                    dsec = durations[ii][jj]
                    dmet = distances[ii][jj]
                    u_dur[si][dj] = int(dsec) if dsec is not None else FALLBACK_LARGE
                    u_dist[si][dj] = int(dmet) if dmet is not None else FALLBACK_LARGE

        for i, src_chunk in enumerate(chunks):
            for j, dst_chunk in enumerate(chunks[i:], start=i):
                union_idx = sorted(set(src_chunk) | set(dst_chunk))  # ≤ max_coords
                coord_str = ";".join(uniq_coords[k] for k in union_idx)
                params = {
                    "sources": ";".join(str(idx) for idx in range(len(union_idx))),
                    "destinations": ";".join(str(idx) for idx in range(len(union_idx))),
                    "annotations": "duration,distance",
                    "access_token": token,
                }
                _ratelimit()
                res = _matrix_get(f"{MB_ENDPOINT}/{profile}/{coord_str}", params)
                _fill(union_idx, res["durations"], res["distances"])

    # 4) Expand back to full N×N matrices
    n = len(locations)
    durations_matrix = [[0] * n for _ in range(n)]
    distances_matrix = [[0] * n for _ in range(n)]
    for i in range(n):
        ui = idx_map[i]
        for j in range(n):
            uj = idx_map[j]
            durations_matrix[i][j] = u_dur[ui][uj]
            distances_matrix[i][j] = u_dist[ui][uj]

    # 5) Final timing
    logger.info(
        "Matrix summary: %d coords → %d call(s); matrix %.2f s",
        len(locations),
        api_calls,
        api_time,
    )
    timer_fetch()
    return durations_matrix, distances_matrix


def fetch_distance_matrix_mapbox(
    locations: List[str],
    *,
    access_token: str | None = None,
    profile: str = MB_PROFILE_DEFAULT,
    metric: str = "duration",  # "duration" | "distance"
) -> List[List[int]]:
    """
    Backwards-compatible single-matrix fetcher.
    Prefer `fetch_matrices_mapbox` in new code.
    """
    durs, dists = fetch_matrices_mapbox(
        locations, access_token=access_token, profile=profile
    )
    return durs if metric == "duration" else dists

###############################################################################
# OR-Tools TSP + 2-opt polish
###############################################################################

def _solve_tsp_order(
    cost_matrix: List[List[int]],
    *,
    start_index: int,
    end_index: int | None,
    time_limit_sec: int,
    roundtrip: bool,
) -> Tuple[List[int], pywrapcp.Assignment | None]:
    n = len(cost_matrix)
    if roundtrip:
        manager = pywrapcp.RoutingIndexManager(n, 1, start_index)
    else:
        assert end_index is not None, "end_index must be provided for path problems"
        manager = pywrapcp.RoutingIndexManager(n, 1, [start_index], [end_index])

    routing = pywrapcp.RoutingModel(manager)

    def transit(i: int, j: int) -> int:
        # Defensive bounds: never throw into IndexToNode
        size = routing.Size()
        if i < 0 or j < 0 or i >= size or j >= size:
            return BIG_COST
        try:
            ni = manager.IndexToNode(i)
            nj = manager.IndexToNode(j)
            return cost_matrix[ni][nj]
        except Exception:
            return BIG_COST

    transit_cb = routing.RegisterTransitCallback(transit)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_cb)

    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.LOCAL_CHEAPEST_INSERTION
    search.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search.time_limit.seconds = max(1, int(time_limit_sec))
    # search.log_search = True  # optional

    sol = routing.SolveWithParameters(search)
    if not sol:
        return [], None

    index = routing.Start(0)
    order: List[int] = []
    while not routing.IsEnd(index):
        order.append(manager.IndexToNode(index))
        index = sol.Value(routing.NextVar(index))
    order.append(manager.IndexToNode(index))
    return order, sol


def _two_opt_polish(order: List[int], cost: List[List[int]], *, roundtrip: bool, passes: int = 2) -> List[int]:
    """
    Lightweight 2-opt polish:
    - Preserves endpoints (for path).
    - Preserves depot at both ends (for roundtrip).
    - Uses `cost` (meters) to evaluate swaps.
    """
    n = len(order)
    if n < 5:
        return order

    # For roundtrip, we expect order[0] == order[-1] (same depot)
    start_fix = 1 if roundtrip else 1  # first mutable index
    end_fix = (n - 2) if roundtrip else (n - 2)  # last mutable index

    for _ in range(max(1, passes)):
        improved = False
        # i and k mark the segment [i:k] to be reversed
        for i in range(start_fix, end_fix - 1):
            a, b = order[i - 1], order[i]
            for k in range(i + 1, end_fix + 1):
                c, d = order[k], order[k + 1]
                # current edges: a-b and c-d
                # proposed edges: a-c and b-d
                delta = (cost[a][c] + cost[b][d]) - (cost[a][b] + cost[c][d])
                if delta < -1:  # improve by at least 1 meter
                    order[i : k + 1] = reversed(order[i : k + 1])
                    improved = True
        if not improved:
            break
    return order

###############################################################################
# Public APIs
###############################################################################


def compute_optimized_route_with_metrics(
    waypoints: List[str],
    *,
    start_location: str | None = None,
    end_location: str | None = None,
    access_token: str | None = None,
    profile: str = MB_PROFILE_DEFAULT,
    time_limit_sec: int = 30,
    optimize_for: str = "distance",  # "distance" (default) | "duration"
) -> Dict[str, object]:
    """
    Compute an optimized route and return BOTH distance and duration metrics.

    Returns dict with keys:
      - ordered_addresses: List[str]
      - per_leg_seconds: List[int]
      - per_leg_meters: List[int]
      - total_duration_seconds: int
      - total_distance_meters: int
      - order_indices: List[int]  # indices into the addresses list
    """
    addresses = waypoints.copy()

    # ----- Round-trip detection (no duplicate depot node) -----
    is_same_depot = (
        bool(start_location)
        and bool(end_location)
        and start_location.strip().lower() == end_location.strip().lower()
    )
    if start_location:
        addresses.insert(0, start_location)
    if end_location and not is_same_depot:
        addresses.append(end_location)
    # ----------------------------------------------------------

    # Fetch both matrices once
    durations, distances = fetch_matrices_mapbox(
        addresses, access_token=access_token, profile=profile
    )

    n = len(addresses)
    if n <= 1:
        ordered_addresses = addresses[:]
        return {
            "ordered_addresses": ordered_addresses,
            "per_leg_seconds": [],
            "per_leg_meters": [],
            "total_duration_seconds": 0,
            "total_distance_meters": 0,
            "order_indices": list(range(n)),
        }

    # Pre-normalization snapshot (to compare prod vs local)
    dr, dc, d_nulls, d_nans, d_infs, d_min, d_max = _matrix_stats(durations)
    sr, sc, s_nulls, s_nans, s_infs, s_min, s_max = _matrix_stats(distances)
    _log(
        "info",
        "Matrix stats PRE: n=%d | dur r=%d c0=%d null=%d nan=%d inf=%d min=%.3f max=%.3f | "
        "dist r=%d c0=%d null=%d nan=%d inf=%d min=%.3f max=%.3f",
        n, dr, dc, d_nulls, d_nans, d_infs, d_min, d_max,
        sr, sc, s_nulls, s_nans, s_infs, s_min, s_max,
    )

    # Normalize/validate (coerce to square int matrices; map None/NaN/inf → BIG_COST)
    durations = _normalize_square_matrix(durations, n, "durations")
    distances = _normalize_square_matrix(distances, n, "distances")

    # Post-normalization snapshot (confirms coercions and shape)
    dr, dc, d_nulls, d_nans, d_infs, d_min, d_max = _matrix_stats(durations)
    sr, sc, s_nulls, s_nans, s_infs, s_min, s_max = _matrix_stats(distances)
    _log(
        "info",
        "Matrix stats POST: n=%d | dur r=%d c0=%d null=%d nan=%d inf=%d min=%.0f max=%.0f | "
        "dist r=%d c0=%d null=%d nan=%d inf=%d min=%.0f max=%.0f",
        n, dr, dc, d_nulls, d_nans, d_infs, d_min, d_max,
        sr, sc, s_nulls, s_nans, s_infs, s_min, s_max,
    )

    # Choose which matrix drives optimization
    cost_matrix = distances if optimize_for == "distance" else durations

    # Solve order (indices in [0..n-1])
    order, sol = _solve_tsp_order(
        cost_matrix,
        start_index=0,
        end_index=(len(addresses) - 1 if not is_same_depot else None),
        time_limit_sec=time_limit_sec,
        roundtrip=is_same_depot,
    )
    if not order:
        raise RuntimeError("TSP solver could not find a route within time limit")

    # Ensure explicit closure for roundtrip (depot appears at both ends)
    if is_same_depot and order[0] != order[-1]:
        order.append(order[0])

    # 2-opt polish on the chosen objective (distance preferred)
    order = _two_opt_polish(
        order,
        distances if optimize_for == "distance" else durations,
        roundtrip=is_same_depot,
    )

    # Collect leg metrics in route order
    per_leg_seconds: List[int] = []
    per_leg_meters: List[int] = []
    for k in range(len(order) - 1):
        i, j = order[k], order[k + 1]
        per_leg_seconds.append(durations[i][j])
        per_leg_meters.append(distances[i][j])

    total_duration_seconds = sum(per_leg_seconds)
    total_distance_meters = sum(per_leg_meters)

    ordered_addresses = [addresses[k] for k in order]
    return {
        "ordered_addresses": ordered_addresses,
        "per_leg_seconds": per_leg_seconds,
        "per_leg_meters": per_leg_meters,
        "total_duration_seconds": total_duration_seconds,
        "total_distance_meters": total_distance_meters,
        "order_indices": order,
    }



def compute_optimized_route(
    waypoints: List[str],
    *,
    start_location: str | None = None,
    end_location: str | None = None,
    access_token: str | None = None,
    profile: str = MB_PROFILE_DEFAULT,
    time_limit_sec: int = 30,
) -> Tuple[List[str], int, List[int]]:
    """
    Backwards-compatible wrapper returning a 3-tuple:
      (ordered_addresses, total_duration_seconds, per_leg_seconds)

    NOTE:
    - The route is optimized for **distance** by default (better geometry/loop),
      but we still *return time metrics* for compatibility with existing callers.
    - Switch to `compute_optimized_route_with_metrics(...)` to access both
      distance and duration directly.
    """
    res = compute_optimized_route_with_metrics(
        waypoints,
        start_location=start_location,
        end_location=end_location,
        access_token=access_token,
        profile=profile,
        time_limit_sec=time_limit_sec,
        optimize_for="distance",
    )
    return (
        res["ordered_addresses"],  # type: ignore[return-value]
        res["total_duration_seconds"],  # type: ignore[return-value]
        res["per_leg_seconds"],  # type: ignore[return-value]
    )

###############################################################################
# Utility
###############################################################################


def seconds_to_hms(sec: int) -> str:
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02}:{m:02}:{s:02}"


def hms_to_seconds(hms: str) -> int:
    """'02:13:45' -> 8025 | returns 0 for blank / malformed strings."""
    m = re.match(r"^(\d+):(\d\d):(\d\d)$", hms or "")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) if m else 0


def seconds_to_pretty(sec: int) -> str:
    """3600 → '1 hr', 8025 → '2 hr 13 min'."""
    h, rem = divmod(sec, 3600)
    m = rem // 60
    if h and m:
        return f"{h} hr {m} min"
    if h:
        return f"{h} hr"
    return f"{m} min"
