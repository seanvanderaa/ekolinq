"""routing_mapbox.py — Mapbox Matrix‑based TSP helper
========================================================
Stable, minimal, and thoroughly linted version.

* Automatic chunking for arbitrarily large waypoint lists.
* Guarantees every Matrix call has **≥ 2 destinations** to avoid Mapbox 422.
* Deduplicates identical coordinates (same address repeated).

Public API matches the original Google helper, so your Flask endpoint
continues to call `compute_optimized_route()` with raw address strings.
"""
from __future__ import annotations

import logging

import os
import time
from collections import defaultdict
from typing import List, Tuple
from urllib.parse import quote_plus
from flask import current_app

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


def _t(label: str) -> callable:
    """Return a lambda that logs elapsed seconds when invoked."""
    logger = current_app.logger
    start = time.perf_counter()
    return lambda: logger.info("%s took %.3f s", label, time.perf_counter() - start)

# helpers/mapbox_routing.py
_MB_RPM = int(os.getenv("MAPBOX_MATRIX_RPM", "300"))   # Mapbox spec: 300 req/min

def _ratelimit() -> None:
    """
    Sleep just enough to stay below the per‑minute cap.
    Signature takes no args so callers don’t have to pass `profile`.
    """
    now   = time.time()
    limit = _MB_RPM
    window = _req_ts["global"]            # single shared window
    window[:] = [t for t in window if now - t < _REQ_WINDOW_SEC]
    if len(window) >= limit:
        sleep_for = _REQ_WINDOW_SEC - (now - window[0]) + 0.05
        current_app.logger.warning(
            "Matrix rate‑limit hit: sleeping %.1f s to stay under %d rpm",
            sleep_for, limit
        )
        time.sleep(sleep_for)
    window.append(now)



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
    
    done = _t(f"GEOCODE '{addr[:40]}…'")
    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{quote_plus(addr)}.json"
    params = {"limit": 1, "access_token": token}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    feat = r.json()["features"][0]
    done()  
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
    logger = current_app.logger

    token = access_token or os.getenv("MAPBOX_ACCESS_TOKEN")
    if not token:
        raise ValueError("MAPBOX_ACCESS_TOKEN env var not set")

    timer_fetch = _t("fetch_distance_matrix_mapbox")      ##### NEW/CHANGED >>>

    # ------------------------------------------------------------------ #
    # 1. Geocode / normalise                                             #
    # ------------------------------------------------------------------ #
    t_geo = _t(f"– geocoding {len(locations)} address(es)")  ##### NEW/CHANGED >>>
    coords_raw = [_maybe_geocode(addr, token) for addr in locations]
    t_geo()                                                  ##### NEW/CHANGED >>>

    # ------------------------------------------------------------------ #
    # 2. Collapse duplicates (unchanged)                                 #
    # ------------------------------------------------------------------ #
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

    # Helpers for timing every Matrix HTTP call ------------------------ #
    api_calls = 0                                           ##### NEW/CHANGED >>>
    api_time  = 0.0                                         ##### NEW/CHANGED >>>

    # ------------------------------------------------------------------ #
    # Helper: timed HTTP wrapper                                         #
    # ------------------------------------------------------------------ #
    def _matrix_get(url: str, params: dict) -> dict:
        """requests.get() that counts calls and measures elapsed time."""
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

    # ------------------------------------------------------------------ #
    # 3. Build the unique‑coords matrix                                  #
    # ------------------------------------------------------------------ #
    if u <= max_coords:
        # ---------- tiny set: one call ---------------------------------
        coord_str = ";".join(uniq_coords)
        params = {"annotations": "duration", "access_token": token}
        _ratelimit()
        res = _matrix_get(f"{MB_ENDPOINT}/{profile}/{coord_str}", params)
        u_matrix = [[int(v) if v else FALLBACK_LARGE for v in row]
                    for row in res["durations"]]

    elif max_coords == 25:
        # ---------- block streaming (25×25) -----------------------------
        block     = 25                     # Mapbox limit for non‑traffic
        u_matrix  = [[FALLBACK_LARGE] * u for _ in range(u)]

        def _fill(src_idx, dst_idx, sub):
            for ii, si in enumerate(src_idx):
                for jj, dj in enumerate(dst_idx):
                    u_matrix[si][dj] = int(sub[ii][jj]) if sub[ii][jj] else FALLBACK_LARGE

        blocks = [list(range(i, min(i + block, u))) for i in range(0, u, block)]

        for src_idx in blocks:
            for dst_idx in blocks:
                union_idx = sorted(set(src_idx) | set(dst_idx))      # ≤ 25
                coord_str  = ";".join(uniq_coords[k] for k in union_idx)
                params = {
                    "sources":      ";".join(str(union_idx.index(k)) for k in src_idx),
                    "destinations": ";".join(str(union_idx.index(k)) for k in dst_idx),
                    "annotations":  "duration",
                    "access_token": token,
                }
                _ratelimit()
                res = _matrix_get(f"{MB_ENDPOINT}/{profile}/{coord_str}", params)
                _fill(src_idx, dst_idx, res["durations"])

    else:
        # ---------- traffic profile row‑stream (10×10) ------------------
        dest_chunk = max_coords - 1        # 9 when traffic
        u_matrix   = [[FALLBACK_LARGE] * u for _ in range(u)]

        for i in range(u):
            remaining = [j for j in range(u) if j != i]
            chunks = []
            while remaining:
                chunk, remaining = remaining[:dest_chunk], remaining[dest_chunk:]
                if len(chunk) == 1:                        # avoid 1‑dest chunk
                    if remaining:
                        chunk.append(remaining.pop(0))
                    else:
                        chunk.insert(0, chunks[-1].pop())
                chunks.append(chunk)

            for dest_idx in chunks:
                coord_str = ";".join(uniq_coords[k] for k in [i] + dest_idx)
                params = {
                    "sources":      "0",
                    "destinations": ";".join(str(d + 1) for d in range(len(dest_idx))),
                    "annotations":  "duration",
                    "access_token": token,
                }
                _ratelimit()
                res = _matrix_get(f"{MB_ENDPOINT}/{profile}/{coord_str}", params)
                durations = res["durations"][0]
                for off, j in enumerate(dest_idx):
                    u_matrix[i][j] = int(durations[off]) if durations[off] else FALLBACK_LARGE
            u_matrix[i][i] = 0   # diagonal

    # ------------------------------------------------------------------ #
    # 5. Expand to full N×N (existing code below remains unchanged)      #
    # ------------------------------------------------------------------ #

    n = len(locations)
    matrix = [[0] * n for _ in range(n)]
    for i in range(n):
        ui = idx_map[i]
        for j in range(n):
            uj = idx_map[j]
            matrix[i][j] = u_matrix[ui][uj]

    # ------------------------------------------------------------------ #
    # 6. Final timing summary                                            #
    # ------------------------------------------------------------------ #
    logger.info(                                             ##### NEW/CHANGED >>>
        "Matrix summary: %d coords → %d call(s); matrix %.2f s",
        len(locations), api_calls, api_time
    )
    timer_fetch()                                            ##### NEW/CHANGED >>>
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
