import math
def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Returns the great-circle distance in METRES between two GPS coordinates.

    Uses the Haversine formula — accurate enough for geofence checks
    (error < 0.5% for distances under 10km).

    Args:
        lat1, lon1: First point (decimal degrees)
        lat2, lon2: Second point (decimal degrees)

    Returns:
        Distance in metres (float)
    """
    EARTH_RADIUS_M = 6_371_000  # metres

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_M * c


def is_within_zone(
    employee_lat: float,
    employee_lon: float,
    zone_lat: float,
    zone_lon: float,
    radius_metres: int,
) -> tuple[bool, float]:
    """
    Checks whether an employee's GPS coordinate falls inside a geofence zone.

    Returns:
        (is_inside: bool, distance_metres: float)
    """
    distance = haversine_distance(employee_lat, employee_lon, zone_lat, zone_lon)
    return distance <= radius_metres, round(distance, 2)
