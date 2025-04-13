import os
import requests
from urllib.parse import urlencode

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

from ortools.constraint_solver import pywrapcp
from ortools.constraint_solver import routing_enums_pb2


def solve_tsp(matrix):
    """
    Solve a basic TSP for the given distance/time matrix using OR-Tools.
    Returns the route as a list of node indices in visiting order.
    
    If round_trip=True, the route starts and ends on index 0.
    If round_trip=False, it starts at index 0 and ends at the last visited.
    """
    print("Solving distance matrix.")
    n = len(matrix)
    
    manager = pywrapcp.RoutingIndexManager(n, 1, 0)
    
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # Settings for the solver
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_parameters.time_limit.seconds = 10  # set a cutoff to avoid infinite search for large problems

    solution = routing.SolveWithParameters(search_parameters)
    if not solution:
        return None

    # Extract the route
    index = routing.Start(0)
    route = []
    while not routing.IsEnd(index):
        route.append(manager.IndexToNode(index))
        index = solution.Value(routing.NextVar(index))
    route.append(manager.IndexToNode(index))  # Add the end location

    return route

def seconds_to_hms(sec):
    hours = sec // 3600
    mins = (sec % 3600) // 60
    if hours > 0:
        return f"{hours} hr {mins} min"
    else:
        return f"{mins} min"
