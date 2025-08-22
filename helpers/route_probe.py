#!/usr/bin/env python3
import os
import sys
import math
import logging
from typing import List, Tuple, Optional

import requests
from flask import Flask, current_app

# Import your production helper so behavior matches the site.
from mapbox_routing import compute_optimized_route

# ----------------------------------------------------------------------
# Config (hardcoded per your notes)
# ----------------------------------------------------------------------
DEPOT = "5389 Mallard Dr., Pleasanton, CA 94566"  # start == end

# ADDRESSES = [
#     "2436 Rivers Bend Circle, Livermore CA",
#     "3103 Belmont Court, Livermore, California 94550, United States",
#     "3531 Germaine Way, Livermore, California 94550, United States",
#     "4057 Sherry Court, Pleasanton, California 94566, United States",
#     "227 Mission Drive, Pleasanton, California 94566, United States",
#     "5786 Shadow Ridge Court, Pleasanton, California 94566, United States",
#     "31 Castledown Road, Pleasanton, California 94566, United States",
#     "3341 Medallion Court, Pleasanton, California 94588, United States",
#     "4639 Sandalwood Drive, Pleasanton, California 94588, United States",
#     "8401 Tiger Lily Drive, San Ramon, California 94582, United States",
#     "704 Brookside Drive, Danville, California 94526, United States",
#     "333 Andora Lane, San Ramon, California 94583, United States",
#     "123 Enchanted Way, San Ramon, California 94583, United States",
#     "627 Hardcastle Court, San Ramon, California 94583, United States",
#     "3580 Ballantyne Drive, Pleasanton, California 94588, United States",
#     "4007 Suffolk Way, Pleasanton, California 94588, United States",
#     "3545 Dickens Court, Pleasanton, California 94588, United States",
#     "2130 Camino Brazos, Pleasanton, California 94566, United States",
#     "5489 Blackbird Drive, Pleasanton, California 94566, United States",
# ]

ADDRESSES = [
    "4326 Quail Run Lane, Danville, CA",
    "536 Sonoma Ave, Livermore, CA",
    "2678 Willowren Way, Pleasanton, CA",
    "5489 Blackbird Drive, Pleasanton, CA",
    "5786 Shadow Ridge Court, Pleasanton, CA",
    "151 Bolla Avenue, Alamo, CA",
    "123 Enchanted Way, San Ramon, CA",
    "333 Andora Lane, San Ramon, CA",
    "1346 Aster Lane, Livermore, CA"
]

PROFILE = "mapbox/driving"
TIME_LIMIT_SEC = 25

# ----------------------------------------------------------------------
# Minimal Flask app just for context + logging
# ----------------------------------------------------------------------
def create_probe_app() -> Flask:
    app = Flask("route_probe")
    try:
        from dotenv import load_dotenv, find_dotenv  # type: ignore
        load_dotenv(find_dotenv())
    except Exception:
        pass

    if not app.logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
    return app

# ----------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------
def ensure_token(logger: logging.Logger) -> str:
    token = os.getenv("MAPBOX_ACCESS_TOKEN")
    if not token:
        logger.error("MAPBOX_ACCESS_TOKEN is not set in the environment.")
        sys.exit(1)
    return token

def haversine_miles(lonlat_a: str, lonlat_b: str) -> float:
    def deg2rad(x: float) -> float: return x * math.pi / 180.0
    lon1, lat1 = map(float, lonlat_a.split(","))
    lon2, lat2 = map(float, lonlat_b.split(","))
    R = 3958.7613  # miles
    dlat = deg2rad(lat2 - lat1)
    dlon = deg2rad(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(deg2rad(lat1))*math.cos(deg2rad(lat2))*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def geocode_norm(addresses: List[str]) -> List[str]:
    # Use the same private helper your app uses (works under app context).
    from mapbox_routing import _maybe_geocode  # type: ignore
    token = os.getenv("MAPBOX_ACCESS_TOKEN")
    return [_maybe_geocode(a, token) for a in addresses]

def pretty_hms(sec: int) -> str:
    h, rem = divmod(sec, 3600)
    m, _ = divmod(rem, 60)
    return f"{h}h {m}m" if h else f"{m}m"

def directions_leg_metrics(
    a_lonlat: str,
    b_lonlat: str,
    token: str,
    profile: str,
    logger: logging.Logger,
) -> Optional[Tuple[float, float]]:
    """
    Returns (distance_meters, duration_seconds) for a->b using Mapbox Directions.
    None if the call fails (we'll log and keep going).
    """
    try:
        base = "https://api.mapbox.com/directions/v5"
        coords = f"{a_lonlat};{b_lonlat}"
        url = f"{base}/{profile}/{coords}"
        params = {
            "alternatives": "false",
            "overview": "false",
            "annotations": "distance,duration",
            "geometries": "geojson",
            "access_token": token,
        }
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        routes = data.get("routes") or []
        if not routes:
            logger.warning("Directions returned no routes for %s -> %s", a_lonlat, b_lonlat)
            return None
        dist_m = float(routes[0].get("distance", 0.0))
        dur_s  = float(routes[0].get("duration", 0.0))
        return dist_m, dur_s
    except Exception as e:
        logger.warning("Directions error for %s -> %s: %s", a_lonlat, b_lonlat, e)
        return None

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main() -> None:
    app = create_probe_app()
    with app.app_context():
        logger = current_app.logger
        token = ensure_token(logger)

        logger.info("Depot (start=end): %s", DEPOT)
        logger.info("Stops (%d): %s", len(ADDRESSES), "; ".join(ADDRESSES))

        # 1) Optimize using your production stack (Matrix-based durations)
        ordered, total_sec_matrix, leg_secs_matrix = compute_optimized_route(
            waypoints=ADDRESSES,
            start_location=DEPOT,
            end_location=DEPOT,
            profile=PROFILE,
            time_limit_sec=TIME_LIMIT_SEC,
        )

        logger.info("Optimized order (start → end):")
        for i, a in enumerate(ordered):
            logger.info("  %2d. %s", i, a)

        # 2) Normalize to lon,lat for Directions calls
        norm = geocode_norm(ordered)
        logger.info("Geocoded (lon,lat):")
        for i, g in enumerate(norm):
            logger.info("  %2d. %s", i, g)

        # 3) Per-leg Directions metrics (distance+duration) vs Matrix duration
        total_dist_m = 0.0
        total_sec_dir = 0.0
        logger.info("Legs (Matrix duration vs Directions distance/duration):")
        for i in range(len(norm) - 1):
            a = norm[i]
            b = norm[i + 1]
            mtx_sec = leg_secs_matrix[i]
            dd = directions_leg_metrics(a, b, token, PROFILE, logger)
            if dd is None:
                logger.info("  %2d -> %2d  matrix=%4ds  directions=unavailable", i, i+1, mtx_sec)
                continue
            dist_m, dir_sec = dd
            total_dist_m += dist_m
            total_sec_dir += dir_sec

            # Warn if durations disagree a lot (helps catch profile/traffic inconsistencies)
            warn = ""
            if mtx_sec and abs(dir_sec - mtx_sec) / max(mtx_sec, 1) > 0.10:
                warn = "  ⚠︎ duration mismatch >10%"
            logger.info(
                "  %2d -> %2d  matrix=%4ds | directions=%4ds, %5.2f mi%s",
                i, i+1, mtx_sec, int(dir_sec), dist_m / 1609.344, warn
            )

        logger.info("Totals:")
        logger.info("  Matrix total time: %s", pretty_hms(int(total_sec_matrix)))
        logger.info("  Directions total time: %s", pretty_hms(int(total_sec_dir)))
        logger.info("  Directions total distance: %.2f mi", total_dist_m / 1609.344)

        # 4) Quick lower-bound sanity (haversine) to spot wild outliers
        total_miles_lb = 0.0
        for i in range(len(norm) - 1):
            total_miles_lb += haversine_miles(norm[i], norm[i+1])
        logger.info("  Straight-line sum (lower bound): ~%.1f mi", total_miles_lb)

if __name__ == "__main__":
    main()
