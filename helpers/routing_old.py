def get_optimized_route(addresses, start_location, api_key=None):
    """
    Round-trip route:
      origin: start_location
      destination: the same start_location
      waypoints: all addresses
    """
    import os, requests
    from urllib.parse import urlencode

    if not api_key:
        api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("Google Maps API key is required")

    if not addresses:
        return [start_location], 0, []

    # Build "optimize:true|..." from ALL addresses
    waypoints_param = "optimize:true|" + "|".join(addresses)

    params = {
        "origin": start_location,
        "destination": start_location,   # same => round trip
        "key": api_key,
        "waypoints": waypoints_param
    }

    url = "https://maps.googleapis.com/maps/api/directions/json?" + urlencode(params)
    response = requests.get(url)
    data = response.json()

    if data["status"] != "OK":
        raise Exception(f"Directions API Error: {data.get('status')} - {data.get('error_message')}")

    route = data["routes"][0]

    waypoint_order = route.get("waypoint_order", [])
    legs = route["legs"]

    total_time_seconds = 0
    leg_times = []
    for leg in legs:
        dur = leg["duration"]["value"]
        total_time_seconds += dur
        leg_times.append(dur)

    # Reconstruct the visited order:
    optimized_order = [start_location]  # you start here
    # Insert the addresses in the optimized order:
    for idx in waypoint_order:
        optimized_order.append(addresses[idx])
    # End back at the start
    optimized_order.append(start_location)

    return optimized_order, total_time_seconds, leg_times
