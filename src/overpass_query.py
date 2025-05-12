import requests
import geopandas as gpd
from shapely.geometry import Point, Polygon, MultiPolygon
from typing import Any, Union


def _prepare_polygon(geometry: Union[Polygon, MultiPolygon], tolerance: float = 0.0001) -> str:
    """
    Simplify and convert a shapely Polygon/MultiPolygon to an Overpass 'poly' string.
    """
    if isinstance(geometry, MultiPolygon):
        poly = geometry.convex_hull
    elif isinstance(geometry, Polygon):
        poly = geometry
    else:
        raise ValueError("geometry must be a Polygon or MultiPolygon")
    simplified = poly.simplify(tolerance, preserve_topology=True)
    coords = []
    for x, y in simplified.exterior.coords:
        coords.extend([str(y), str(x)])  # lat, lon order for Overpass
    return " ".join(coords)


def _build_overpass_query(poly_str: str, query_params: list[tuple[str, str]]) -> str:
    """
    Construct the Overpass QL query string from a polygon string and tag filters.
    """
    lines = [f'nwr["{k}"="{v}"](poly:"{poly_str}");' for k, v in query_params]
    body = "\n".join(lines)
    query = f"""
    [out:json][timeout:25];
    (
      {body}
    );
    out body;
    >;
    out skel qt;
    """
    return query


def _fetch_overpass_data(query: str, endpoint: str = "http://overpass-api.de/api/interpreter") -> list[dict[str, Any]]:
    """
    Send a GET request to Overpass API and return the elements list.
    """
    resp = requests.get(endpoint, params={"data": query})
    resp.raise_for_status()
    data = resp.json()
    return data.get("elements", [])


def _build_node_index(elements: list[dict[str, Any]]) -> dict[int, tuple[float, float]]:
    """
    Create a mapping from node ID to (lon, lat) coordinates.
    """
    return {el["id"]: (el["lon"], el["lat"])
            for el in elements if el["type"] == "node"}


def _extract_features(elements: list[dict[str, Any]], node_index: dict[int, tuple[float, float]]) -> list[dict[str, Any]]:
    """
    Convert raw Overpass elements into a list of feature dicts
    with flattened tags and shapely Point geometries.
    """
    features = []
    for el in elements:
        tags = el.get("tags")
        if not tags:
            continue
        geom = None
        if el["type"] == "node":
            geom = Point(el["lon"], el["lat"])
        elif el["type"] == "way":
            pts = [node_index.get(n) for n in el.get("nodes", [])]
            pts = [p for p in pts if p is not None]
            if len(pts) >= 3:
                geom = Polygon(pts)
        if geom is None:
            continue
        # reduce polygons to centroids
        if isinstance(geom, (Polygon, MultiPolygon)):
            geom = geom.centroid
        feat = tags.copy()
        feat["geometry"] = geom
        features.append(feat)
    return features


def _build_gdf(features: list[dict[str, Any]], crs: str = "EPSG:4326") -> gpd.GeoDataFrame:
    """
    Construct a GeoDataFrame from a list of feature dicts.
    """
    return gpd.GeoDataFrame(features, crs=crs)


def query_overpass_candidates(
    geometry: Union[Polygon, MultiPolygon],
    query_params: list[tuple[str, str]] = [("amenity", "parking")]
) -> gpd.GeoDataFrame:
    """
    Main entry: Query multiple OSM tags within a given shapely geometry,
    returning a GeoDataFrame of candidate sites.
    """
    poly_str = _prepare_polygon(geometry)
    query = _build_overpass_query(poly_str, query_params)
    elements = _fetch_overpass_data(query)
    node_idx = _build_node_index(elements)
    features = _extract_features(elements, node_idx)
    gdf = _build_gdf(features)
    return gdf
