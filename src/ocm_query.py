# src/ocm_query.py

import requests
from shapely.geometry import Polygon, MultiPolygon, Point
from typing import Union
import geopandas as gpd
import pandas as pd
import polyline  # Added for encoding


def _simplify_polygon_for_ocm(
    geometry: Union[Polygon, MultiPolygon], tolerance: float = 0.001
) -> list[tuple[float, float]]:
    if isinstance(geometry, MultiPolygon):
        geometry = geometry.convex_hull
    if not isinstance(geometry, Polygon):
        raise ValueError("Expected Polygon or MultiPolygon")
    simplified = geometry.simplify(tolerance, preserve_topology=True)
    # Return as list of (lat, lon) for polyline encoding
    return [(float(lat), float(lon)) for lon, lat in simplified.exterior.coords]


def get_charging_points_by_polygon(
    geometry: Union[Polygon, MultiPolygon],
    max_results: int,
    api_key: str = "8ac12fe1-9303-4b3d-b0cc-87713c6c66a0",
):
    simplified_coords = _simplify_polygon_for_ocm(geometry)
    encoded_polyline = polyline.encode(simplified_coords)
    print(f"Encoded polyline: {encoded_polyline}")
    url = "https://api.openchargemap.io/v3/poi/"
    params = {
        "polygon": encoded_polyline,
        "maxresults": max_results,
        "output": "json",
    }
    headers = {"X-API-Key": api_key}
    response = requests.get(url, params=params, headers=headers)
    if response.status_code != 200:
        raise Exception(f"API request failed: {response.status_code} - {response.text}")

    # Flatten structure for easier tabular display
    points = response.json()

    data = []
    for point in points:
        address = point.get("AddressInfo", {})
        data.append(
            {
                "id": point.get("ID"),
                "title": address.get("Title"),
                "address": address.get("AddressLine1"),
                "town": address.get("Town"),
                "state": address.get("StateOrProvince"),
                "country": address.get("CountryID"),
                "latitude": address.get("Latitude"),
                "longitude": address.get("Longitude"),
                "url": address.get("RelatedURL"),
                "power_kw": [
                    conn.get("PowerKW") for conn in point.get("Connections", [])
                ],
                "num_points": point.get("NumberOfPoints"),
            }
        )

    df = pd.DataFrame(data)

    # if df is empty, return an empty GeoDataFrame
    if df.empty:
        return gpd.GeoDataFrame(
            columns=[
                "id",
                "title",
                "address",
                "town",
                "state",
                "country",
                "latitude",
                "longitude",
                "url",
                "power_kw",
                "num_points",
                "geometry",
            ]
        )
    df = df[(df["latitude"] != 0) & (df["longitude"] != 0)]

    # Create geometry column
    geometry = [Point(xy) for xy in zip(df["longitude"], df["latitude"])]
    gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")

    return gdf
