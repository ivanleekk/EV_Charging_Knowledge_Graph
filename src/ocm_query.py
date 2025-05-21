import requests
from shapely.geometry import Polygon, MultiPolygon


def get_charging_points_by_polygon(
    geometry, max_results=10, api_key="8ac12fe1-9303-4b3d-b0cc-87713c6c66a0"
):
    """
    Fetch charging points within a polygon or multipolygon geometry.

    Args:
        geometry (Polygon or MultiPolygon): A Shapely geometry object.
        max_results (int): Maximum number of results to return.
        api_key (str): Optional API key for OpenChargeMap.

    Returns:
        list: List of charging point results from the API.
    """
    if isinstance(geometry, Polygon):
        polygons = [geometry]
    elif isinstance(geometry, MultiPolygon):
        polygons = list(geometry.geoms)
    else:
        raise TypeError("geometry must be a shapely Polygon or MultiPolygon")

    # Flatten exterior coordinates of all polygons into a single list of (lat, lon)
    polygon_points = []
    for poly in polygons:
        coords = list(poly.exterior.coords)
        # Shapely uses (lon, lat); OpenChargeMap expects (lat, lon)
        polygon_points.extend([(lat, lon) for lon, lat in coords])

    # Format polygon as comma-separated lat/lon pairs
    polygon_str = ",".join(f"{lat},{lon}" for lat, lon in polygon_points)

    url = "https://api.openchargemap.io/v3/poi/"
    params = {
        "polygon": polygon_str,
        "maxresults": max_results,
    }
    headers = {"X-API-Key": api_key}

    response = requests.get(url, params=params, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"API request failed: {response.status_code} - {response.text}")
