"""Routing helper functions using Mapbox Matrix API (traffic‑aware).

Core ideas
----------
* Mapbox Matrix API limits the number of *coordinates* in a single request –
  • 25 for profiles ``mapbox/driving``, ``mapbox/walking``, ``mapbox/cycling``
  • 10 for ``mapbox/driving-traffic`` (live‑traffic)

* We therefore build the N×N time matrix by **streaming rows**:
  – Call the API with **one origin** plus up to (MAX_COORDS‑1) destinations.
  – Chunk the destination list so union(origin,dests) ≤ MAX_COORDS.
  – Fill the matrix as we go.

* Element‑based billing remains low (≤ N² per full matrix).
* Works for any N (you are bound only by free‑tier 100 k elements/month).
"""
from __future__ import annotations
import os
import time
import requests
from collections import defaultdict
from typing import List, Tuple
from urllib.parse import quote_plus
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

###############################################################################
# Config & helpers
###############################################################################

MB_PROFILE_DEFAULT = "mapbox/driving-traffic"  # change to "mapbox/driving" if you don’t need traffic
MB_ENDPOINT = "https://api.mapbox.com/directions-matrix/v1"
FALLBACK_LARGE = 999_999  # seconds when no route exists

# Rate‑limit guard: Mapbox Matrix => 30 req/min for driving‑traffic, 60 for others.
# We keep a sliding‑window counter keyed by profile to avoid 429s.
_REQ_WINDOW_SEC = 60
_req_timestamps: defaultdict[str, List[float]] = defaultdict(list)

def _ratelimit(profile: str):
    limit = 30 if profile.endswith("traffic") else 60
    now = time.time()
    window = _req_timestamps[profile]
    window[:] = [t for t in window if now - t < _REQ_WINDOW_SEC]
    if len(window) >= limit:
        sleep_for = _REQ_WINDOW_SEC - (now - window[0]) + 0.1
        time.sleep(max(0, sleep_for))
    window.append(time.time())

def _maybe_geocode(location: str, token: str) -> str:
    """Return "lon,lat" for a textual address (or already‑formatted coord)."""
    if "," in location and location.replace("-", "").replace(",", "").replace(".", "").replace(" ", "").isdigit():
        return location  # assume already "lon,lat"
    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{quote_plus(location)}.json"
    params = {"limit": 1, "access_token": token}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    feat = resp.json()["features"][0]
    lon, lat = feat["center"]
    return f"{lon},{lat}"

###############################################################################
# Matrix fetcher with automatic chunking
###############################################################################

def fetch_distance_matrix_mapbox(
    locations: List[str],
    *,
    access_token: str | None = None,
    profile: str = MB_PROFILE_DEFAULT,
) -> List[List[int]]:
    """Return full *N×N* travel‑time matrix (seconds) using the Mapbox Matrix API.

    The function transparently handles **duplicate addresses / coordinates** (which
    otherwise yield a 422 *InvalidInput* error) by collapsing duplicates before
    it calls the API and then expanding the matrix back to the original size.

    Parameters
    ----------
    locations
        Sequence of either free‑form address strings *or* "lon,lat" strings.
    access_token
        Mapbox token. If ``None`` we fall back to ``MAPBOX_ACCESS_TOKEN`` env var.
    profile
        Routing profile. Defaults to ``mapbox/driving-traffic``.
    """
    if access_token is None:
        access_token = os.environ.get("MAPBOX_ACCESS_TOKEN")
    if not access_token:
        raise ValueError("Missing Mapbox access token (MAPBOX_ACCESS_TOKEN)")

    # ------------------------------------------------------------------
    # 1) Forward‑geocode every location -> "lon,lat" strings
    # ------------------------------------------------------------------
    coords_raw = [_maybe_geocode(loc, access_token) for loc in locations]

    # ------------------------------------------------------------------
    # 2) Collapse **duplicate coordinate strings** to avoid API 422 errors
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

    max_coords = 10 if profile.endswith("traffic") else 25

    # ------------------------------------------------------------------
    # Fast‑path: if everything fits in ONE call, do that → avoids "1 element"
    # error when u == 2 (Mapbox requires ≥ 2 elements per request).
    # ------------------------------------------------------------------
    if u <= max_coords:
        coord_str = ";".join(uniq_coords)
        url = f"{MB_ENDPOINT}/{profile}/{coord_str}"
        params = {"annotations": "duration", "access_token": access_token}
        _ratelimit(profile)
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "Ok":
            raise RuntimeError(f"Matrix API error: {data.get('code')} – {data.get('message')}")
        durations_2d = data["durations"]
        u_matrix: list[list[int]] = []
        for row in durations_2d:
            u_matrix.append([int(v) if v is not None else FALLBACK_LARGE for v in row])
    else:
        # ------------------------------------------------------------------
        # 3) Stream‑fetch the *u×u* matrix row‑by‑row, chunked by API limit
        # ------------------------------------------------------------------
        dest_chunk = max_coords - 1  # reserve first slot for origin
        u_matrix: list[list[int | None]] = [[None] * u for _ in range(u)]

        for i in range(u):
            others = list(range(u))
            others.remove(i)
            for start in range(0, len(others), dest_chunk):
                dest_idx = others[start : start + dest_chunk]
                if not dest_idx:
                    continue  # shouldn't happen, but guard anyway
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
                    try:
                        err = resp.json()
                        raise RuntimeError(
                            f"Matrix API InvalidInput – {err.get('message', 'no details')}"
                        )
                    except ValueError:
                        resp.raise_for_status()
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") != "Ok":
                    raise RuntimeError(f"Matrix API error: {data.get('code')} – {data.get('message')}")
                durations = data["durations"][0]
                for off, j in enumerate(dest_idx):
                    dur = durations[off]
                    u_matrix[i][j] = int(dur) if dur is not None else FALLBACK_LARGE
            u_matrix[i][i] = 0

        # Any None → large penalty
        for i in range(u):
            for j in range(u):
                if u_matrix[i][j] is None:
                    u_matrix[i][j] = 0 if i == j else FALLBACK_LARGE
        others = list(range(u))
        others.remove(i)
        for start in range(0, len(others), dest_chunk):
            dest_idx = others[start : start + dest_chunk]
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
                # Bubble up a more useful message from the body, if present
                try:
                    err = resp.json()
                    raise RuntimeError(
                        f"Matrix API InvalidInput – {err.get('message', 'no details')}"
                    )
                except ValueError:
                    resp.raise_for_status()
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != "Ok":
                raise RuntimeError(f"Matrix API error: {data.get('code')} – {data.get('message')}")
            durations = data["durations"][0]
            for off, j in enumerate(dest_idx):
                dur = durations[off]
                u_matrix[i][j] = int(dur) if dur is not None else FALLBACK_LARGE
        u_matrix[i][i] = 0

    # Fill any remaining None (shouldn’t happen unless API returns null for same‑point route)
    for i in range(u):
        for j in range(u):
            if u_matrix[i][j] is None:
                u_matrix[i][j] = 0 if i == j else FALLBACK_LARGE

    # ------------------------------------------------------------------
    # 4) Expand back to *N×N* full matrix, duplicating rows/cols as needed
    # ------------------------------------------------------------------
    n = len(locations)
    matrix: list[list[int]] = [[0] * n for _ in range(n)]
    for i in range(n):
        ui = idx_map[i]
        for j in range(n):
            uj = idx_map[j]
            matrix[i][j] = u_matrix[ui][uj]  # type: ignore[literal-required]

    return matrix

###############################################################################
# OR‑Tools TSP wrapper (unchanged except for fetcher)
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
    addresses = waypoints[:]
    if start_location:
        addresses.insert(0, start_location)
    if end_location:
        addresses.append(end_location)

    matrix = fetch_distance_matrix_mapbox(addresses, access_token=access_token, profile=profile)

    n = len(addresses)
    mgr = pywrapcp.RoutingIndexManager(n, 1, [0], [n - 1])
    routing = pywrapcp.RoutingModel(mgr)

    transit_cb = routing.RegisterTransitCallback(lambda i, j: matrix[mgr.IndexToNode(i)][mgr.IndexToNode(j)])
    routing.SetArcCostEvaluatorOfAllVehicles(transit_cb)

    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search.time_limit.seconds = time_limit_sec

    solution = routing.SolveWithParameters(search)
    if not solution:
        raise RuntimeError("TSP solver failed to find a route")

    # Extract order
    idx, order = routing.Start(0), []
    while not routing.IsEnd(idx):
        order.append(mgr.IndexToNode(idx))
        idx = solution.Value(routing.NextVar(idx))
    order.append(mgr.IndexToNode(idx))

    ordered_addresses = [addresses[i] for i in order]
    leg_times = [matrix[order[k]][order[k + 1]] for k in range(len(order) - 1)]
    return ordered_addresses, sum(leg_times), leg_times

###############################################################################
# Simple pretty‑printer
###############################################################################

def seconds_to_hms(sec: int) -> str:
    h, m = divmod(sec, 3600)
    m //= 60
    return f"{h} hr {m} min" if h else f"{m} min"
