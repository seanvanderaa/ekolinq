"""routing_mapbox.py — Mapbox Matrix‑based TSP helper
========================================================
Stable, minimal, and thoroughly linted version.

* **Traffic‑aware** by default (`mapbox/driving-traffic`, 10 coords.request).
* Automatic chunking for arbitrarily large waypoint lists.
* Guarantees every Matrix call has **≥ 2 destinations** to avoid Mapbox 422.
* Deduplicates identical coordinates (same address repeated).

Public API matches the original Google helper, so your Flask endpoint
continues to call `compute_optimized_route()` with raw address strings.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import List, Tuple
from urllib.parse import quote_plus

import requests
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

###############################################################################
# Constants & utilities
###############################################################################

MB_PROFILE_DEFAULT = "mapbox/driving"  # 10 coords/call -traffic
MB_ENDPOINT = "https://api.mapbox.com/directions-matrix/v1"
FALLBACK_LARGE = 999_999  # penalty (seconds) for unreachable legs
_REQ_WINDOW_SEC = 60      # coarse rate‑limit window
_req_ts: defaultdict[str, List[float]] = defaultdict(list)

def _ratelimit(profile: str) -> None:
    """Sleep just enough to stay within Mapbox per‑minute quotas."""
    limit = 30 if profile.endswith("traffic") else 60
    now = time.time()
    window = _req_ts[profile]
    window[:] = [t for t in window if now - t < _REQ_WINDOW_SEC]
    if len(window) >= limit:
        time.sleep(_REQ_WINDOW_SEC - (now - window[0]) + 0.05)
    window.append(time.time())

def _coords_like(s: str) -> bool:
    try:
        lon, lat, *_ = s.split(",")
        float(lon); float(lat)
        return True
    except Exception:
        return False

def _maybe_geocode(addr: str, token: str) -> str:
    if _coords_like(addr):
        return addr  # already "lon,lat"
    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{quote_plus(addr)}.json"
    params = {"limit": 1, "access_token": token}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    feat = r.json()["features"][0]
    lon, lat = feat["center"]
    return f"{lon},{lat}"

###############################################################################
# Matrix builder
###############################################################################

def fetch_distance_matrix_mapbox(
    locations: List[str],
    *,
    access_token: str | None = None,
    profile: str = MB_PROFILE_DEFAULT,
) -> List[List[int]]:
    """Return an *N×N* travel‑time matrix (seconds) via Mapbox Matrix API."""

    token = access_token or os.getenv("MAPBOX_ACCESS_TOKEN")
    if not token:
        raise ValueError("MAPBOX_ACCESS_TOKEN env var not set")

    # -- 1. Geocode / normalise ------------------------------------------------
    coords_raw = [_maybe_geocode(addr, token) for addr in locations]

    # -- 2. Collapse duplicates ------------------------------------------------
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

    max_coords = 10 if profile.endswith("traffic") else 25

    # -- 3. Fast path: single call suffices -----------------------------------
    if u <= max_coords:
        coord_str = ";".join(uniq_coords)
        params = {"annotations": "duration", "access_token": token}
        _ratelimit(profile)
        r = requests.get(f"{MB_ENDPOINT}/{profile}/{coord_str}", params=params, timeout=15)
        r.raise_for_status()
        res = r.json()
        if res.get("code") != "Ok":
            raise RuntimeError(f"Matrix API error: {res.get('message')}")
        u_matrix = [[int(v) if v else FALLBACK_LARGE for v in row] for row in res["durations"]]
    else:
        # -- 4. Row‑stream for large sets --------------------------------------
        dest_chunk = max_coords - 1  # 1 slot reserved for origin
        u_matrix: List[List[int]] = [[FALLBACK_LARGE] * u for _ in range(u)]
        for i in range(u):
            remaining = [j for j in range(u) if j != i]
            chunks: List[List[int]] = []
            while remaining:
                chunk = remaining[:dest_chunk]
                remaining = remaining[dest_chunk:]
                # Avoid 1‑element chunk (would yield 1 matrix element error)
                if len(chunk) == 1:
                    if remaining:
                        chunk.append(remaining.pop(0))
                    else:
                        # borrow from previous chunk
                        chunk.insert(0, chunks[-1].pop())
                chunks.append(chunk)
            # API calls
            for dest_idx in chunks:
                coord_str = ";".join(uniq_coords[k] for k in [i] + dest_idx)
                params = {
                    "sources": "0",
                    "destinations": ";".join(str(d + 1) for d in range(len(dest_idx))),
                    "annotations": "duration",
                    "access_token": token,
                }
                _ratelimit(profile)
                r = requests.get(f"{MB_ENDPOINT}/{profile}/{coord_str}", params=params, timeout=15)
                if r.status_code == 422:
                    raise RuntimeError(f"Matrix API InvalidInput – {r.json().get('message','')}" )
                r.raise_for_status()
                res = r.json()
                if res.get("code") != "Ok":
                    raise RuntimeError(f"Matrix API error: {res.get('message')}")
                durations = res["durations"][0]
                for off, j in enumerate(dest_idx):
                    u_matrix[i][j] = int(durations[off]) if durations[off] else FALLBACK_LARGE
            u_matrix[i][i] = 0

    # -- 5. Expand to full N×N -------------------------------------------------
    n = len(locations)
    matrix = [[0] * n for _ in range(n)]
    for i in range(n):
        ui = idx_map[i]
        for j in range(n):
            uj = idx_map[j]
            matrix[i][j] = u_matrix[ui][uj]
    return matrix

###############################################################################
# OR‑Tools TSP wrapper (identical public signature)
###############################################################################

def compute_optimized_route(
    waypoints: List[str],
    *,
    start_location: str | None = None,
    end_location: str | None = None,
    access_token: str | None = None,
    profile: str = MB_PROFILE_DEFAULT,
    time_limit_sec: int = 10,
) -> Tuple[List[str], int, List[int]]:
    """Return (ordered_addresses, total_duration_seconds, per_leg_seconds)."""
    addresses = waypoints.copy()
    if start_location:
        addresses.insert(0, start_location)
    if end_location:
        addresses.append(end_location)

    matrix = fetch_distance_matrix_mapbox(addresses, access_token=access_token, profile=profile)

    n = len(addresses)
    manager = pywrapcp.RoutingIndexManager(n, 1, [0], [n - 1])
    routing = pywrapcp.RoutingModel(manager)

    transit_cb = routing.RegisterTransitCallback(
        lambda i, j: matrix[manager.IndexToNode(i)][manager.IndexToNode(j)]
    )
    routing.SetArcCostEvaluatorOfAllVehicles(transit_cb)

    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search.time_limit.seconds = time_limit_sec

    sol = routing.SolveWithParameters(search)
    if not sol:
        raise RuntimeError("TSP solver could not find a route within time limit")

    idx = routing.Start(0)
    order: List[int] = []
    while not routing.IsEnd(idx):
        order.append(manager.IndexToNode(idx))
        idx = sol.Value(routing.NextVar(idx))
    order.append(manager.IndexToNode(idx))

    ordered_addresses = [addresses[k] for k in order]
    leg_secs = [matrix[order[k]][order[k + 1]] for k in range(len(order) - 1)]
    return ordered_addresses, sum(leg_secs), leg_secs

###############################################################################
# Utility
###############################################################################

def seconds_to_hms(sec: int) -> str:
    h, rem = divmod(sec, 3600)
    m = rem // 60
    return f"{h} hr {m} min" if h else f"{m} min"
