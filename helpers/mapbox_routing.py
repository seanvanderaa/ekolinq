"""routing_mapbox.py – Compute optimized routes using Mapbox Matrix API
=======================================================================
Drop‑in replacement for the former Google DistanceMatrix helper.
Handles:
* live‑traffic (default profile ``mapbox/driving-traffic`` – 10 coords/call)
* automatic chunking for >10 or >25 points (depending on profile)
* duplicate addresses/coordinates
* Mapbox "1‑matrix‑element" 422 error by ensuring each request has ≥2 elements
* basic rate‑limit smoothing (30 req/min for traffic, 60 for non‑traffic)
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
# Constants & simple helpers
###############################################################################

MB_PROFILE_DEFAULT = "mapbox/driving-traffic"  # change to "mapbox/driving" if you don't need traffic
MB_ENDPOINT = "https://api.mapbox.com/directions-matrix/v1"
FALLBACK_LARGE = 999_999  # large penalty (seconds) when no route exists

_REQ_WINDOW_SEC = 60  # sliding window for rudimentary rate‑limit handling
_req_timestamps: defaultdict[str, List[float]] = defaultdict(list)


def _ratelimit(profile: str) -> None:
    """Sleep if we would exceed Mapbox per‑minute request caps."""
    limit = 30 if profile.endswith("traffic") else 60
    now = time.time()
    window = _req_timestamps[profile]
    window[:] = [t for t in window if now - t < _REQ_WINDOW_SEC]
    if len(window) >= limit:
        time.sleep(_REQ_WINDOW_SEC - (now - window[0]) + 0.1)
    window.append(time.time())


def _maybe_geocode(location: str, token: str) -> str:
    """Return "lon,lat" for an address or pass through if already that form."""
    if (
        "," in location
        and all(p.replace("-", "").replace(".", "").isdigit() for p in location.split(","))
    ):
        return location  # looks like "-121.3,37.6"
    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{quote_plus(location)}.json"
    params = {"limit": 1, "access_token": token}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    feat = resp.json()["features"][0]
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
    """Return full *N×N* travel‑time matrix (seconds) via Mapbox Matrix API."""

    # ------------------------------------------------------------------
    # 0) Access token
    # ------------------------------------------------------------------
    if access_token is None:
        access_token = os.environ.get("MAPBOX_ACCESS_TOKEN")
    if not access_token:
        raise ValueError("MAPBOX_ACCESS_TOKEN not found in env or args")

    # ------------------------------------------------------------------
    # 1) Geocode → lon,lat strings
    # ------------------------------------------------------------------
    coords_raw = [_maybe_geocode(addr, access_token) for addr in locations]

    # ------------------------------------------------------------------
    # 2) Collapse duplicates so Mapbox doesn't 422 on identical coords
    # ------------------------------------------------------------------
    coord_to_uidx: dict[str, int] = {}
    uniq_coords: list[str] = []
    idx_map: list[int] = []  # original index -> unique index

    for c in coords_raw:
        if c not in coord_to_uidx:
            coord_to_uidx[c] = len(uniq_coords)
            uniq_coords.append(c)
        idx_map.append(coord_to_uidx[c])

    u = len(uniq_coords)
    if u < 2:
        raise ValueError("Need at least two distinct coordinates to build a matrix")

    max_coords = 10 if profile.endswith("traffic") else 25

    # ------------------------------------------------------------------
    # 3) Fast path – single call covers all coords (and Mapbox allows it)
    # ------------------------------------------------------------------
    if u <= max_coords:
        coord_str = ";".join(uniq_coords)
        params = {"annotations": "duration", "access_token": access_token}
        url = f"{MB_ENDPOINT}/{profile}/{coord_str}"
        _ratelimit(profile)
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "Ok":
            raise RuntimeError(f"Matrix API error: {data.get('code')} – {data.get('message')}")
        durations = data["durations"]
        u_matrix = [
            [int(v) if v is not None else FALLBACK_LARGE for v in row] for row in durations
        ]
    else:
        # ------------------------------------------------------------------
        # 4) Row‑stream approach for larger sets
        # ------------------------------------------------------------------
        dest_chunk = max_coords - 1  # keep first slot for the origin
        u_matrix: list[list[int | None]] = [[None] * u for _ in range(u)]

        for i in range(u):
            others = list(range(u))
            others.remove(i)

            # Slice into chunks but make sure final chunk length ≠ 1
            chunks: list[list[int]] = [
                others[k : k + dest_chunk] for k in range(0, len(others), dest_chunk)
            ]
            if len(chunks) > 1 and len(chunks[-1]) == 1:
                chunks[-2].append(chunks[-1][0])  # steal one
                chunks.pop()

            for dest_idx in chunks:
                call_indices = [i] + dest_idx
                coord_str = ";".join(uniq_coords[k] for k in call_indices)
                params = {
                    "sources": "0",
                    "destinations": ",".join(str(j + 1) for j in range(len(dest_idx))),
                    "annotations": "duration",
                    "access_token": access_token,
                }
                url = f"{MB_ENDPOINT}/{profile}/{coord_str}"
                _ratelimit(profile)
                resp = requests.get(url, params=params, timeout=15)
                if resp.status_code == 422:
                    err_msg = resp.json().get("message", "no details")
                    raise RuntimeError(f"Matrix API InvalidInput – {err_msg}")
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") != "Ok":
                    raise RuntimeError(
                        f"Matrix API error: {data.get('code')} – {data.get('message')}"
                    )
                durations = data["durations"][0]
                for off, j in enumerate(dest_idx):
                    u_matrix[i][j] = (
                        int(durations[off]) if durations[off] is not None else FALLBACK_LARGE
                    )
            u_matrix[i][i] = 0

        # Fill any None slots
        for r in range(u):
            for c in range(u):
                if u_matrix[r][c] is None:
                    u_matrix[r][c] = 0 if r == c else FALLBACK_LARGE

    # ------------------------------------------------------------------
    # 5) Expand back to full N×N using idx_map
    # ------------------------------------------------------------------
    n = len(locations)
    matrix = [[0] * n for _ in range(n)]
    for i in range(n):
        ui = idx_map[i]
        for j in range(n):
            uj = idx_map[j]
            matrix[i][j] = u_matrix[ui][uj]

    return matrix

###############################################################################
# OR‑Tools wrapper – unchanged interface vs. Google version
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
    """Return (ordered_addresses, total_seconds, per_leg_seconds)."""

    addresses = list(waypoints)
    if start_location:
        addresses.insert(0, start_location)
    if end_location:
        addresses.append(end_location)

    matrix = fetch_distance_matrix_mapbox(
        addresses, access_token=access_token, profile=profile
    )

    n = len(addresses)
    mgr = pywrapcp.RoutingIndexManager(n, 1, [0], [n - 1])
    routing = pywrapcp.RoutingModel(mgr)

    transit_cb = routing.RegisterTransitCallback(
        lambda i, j: matrix[mgr.IndexToNode(i)][mgr.IndexToNode(j)]
    )
    routing.SetArcCostEvaluatorOfAllVehicles(transit_cb)

    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search.time_limit.seconds = time_limit_sec

    solution = routing.SolveWithParameters(search)
    if not solution:
        raise RuntimeError("TSP solver failed to find a route")

    order = []
    idx = routing.Start(0)
    while not routing.IsEnd(idx):
        order.append(mgr.IndexToNode(idx))
        idx = solution.Value(routing.NextVar(idx))
    order.append(mgr.IndexToNode(idx))  # end node

    ordered_addresses = [addresses[i] for i in order]
    leg_times = [matrix[order[k]][order[k + 1]] for k in range(len(order) - 1)]

    return ordered_addresses, sum(leg_times), leg_times

###############################################################################
# Small util – hours/mins formatter
###############################################################################

def seconds_to_hms(sec: int) -> str:
    h, m = divmod(sec, 3600)
    m //= 60
    return f"{h} hr {m} min" if h else f"{m} min"
