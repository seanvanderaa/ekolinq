import os
import requests
from urllib.parse import urlencode
from ortools.constraint_solver import pywrapcp, routing_enums_pb2


def fetch_distance_matrix(locations, api_key=None):
    """
    Fetch a traffic-based distance matrix (in *seconds*).
    `locations` = list of address strings or lat-lng strings.
    Returns a 2D list: matrix[i][j] is the travel time in seconds from i->j.
    """
    print("Fetching distance matrix from Google.")
    if not api_key:
        api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise ValueError("Missing Google Maps API key.")

    # Build request
    params = {
        "origins": "|".join(locations),
        "destinations": "|".join(locations),
        "departure_time": "now",      # for live/real-time traffic
        "traffic_model": "best_guess",
        "key": api_key
    }

    url = "https://maps.googleapis.com/maps/api/distancematrix/json?" + urlencode(params)
    response = requests.get(url)
    data = response.json()

    if data["status"] != "OK":
        raise Exception(f"Distance Matrix Error: {data.get('status')} - {data.get('error_message')}")

    rows = data["rows"]
    n = len(locations)
    matrix = [[0]*n for _ in range(n)]

    for i in range(n):
        elements = rows[i]["elements"]
        for j in range(n):
            if elements[j]["status"] != "OK":
                matrix[i][j] = 999999  # or some large penalty
            else:
                matrix[i][j] = elements[j]["duration"]["value"]  # seconds
    
    return matrix

def compute_optimized_route(
    waypoints: list[str],
    *,
    start_location: str | None = None,
    end_location: str | None = None,
    api_key: str | None = None,
    time_limit_sec: int = 10,
) -> tuple[list[str], int, list[int]]:
    """
    Returns (sorted_addresses, total_seconds, per_leg_seconds).

    *All* addresses **including** start/end must be valid, cleaned strings.
    Raises on Google/solver error so the caller can fall back gracefully.
    """
    # Build the full ordered list fed to the solver
    addresses = waypoints[:]
    if start_location:
        addresses.insert(0, start_location)
    if end_location:
        addresses.append(end_location)

    matrix = fetch_distance_matrix(addresses, api_key)

    # --- OR-Tools solver with fixed start / fixed end -------------
    n = len(addresses)
    end_idx = n - 1
    mgr = pywrapcp.RoutingIndexManager(n, 1, [0], [end_idx])
    routing = pywrapcp.RoutingModel(mgr)

    def _cb(i, j):
        return matrix[mgr.IndexToNode(i)][mgr.IndexToNode(j)]

    transit = routing.RegisterTransitCallback(_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit)
    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search.time_limit.seconds = time_limit_sec

    sol = routing.SolveWithParameters(search)
    if not sol:
        raise RuntimeError("TSP solver failed to find a route")

    idx, order = routing.Start(0), []
    while not routing.IsEnd(idx):
        order.append(mgr.IndexToNode(idx))
        idx = sol.Value(routing.NextVar(idx))
    order.append(mgr.IndexToNode(idx))        # append end

    sorted_addrs = [addresses[i] for i in order]
    leg_times   = [matrix[order[i]][order[i+1]] for i in range(len(order)-1)]
    total_sec   = sum(leg_times)
    return sorted_addrs, total_sec, leg_times


# -----------------------------------------------------------------
def seconds_to_hms(sec: int) -> str:
    h, m = divmod(sec, 3600)
    m //= 60
    return f"{h} hr {m} min" if h else f"{m} min"