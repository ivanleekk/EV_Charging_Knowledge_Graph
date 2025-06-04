import requests
import geopandas as gpd
from shapely.geometry import Point, Polygon, MultiPolygon
from typing import Any, Union
import time


def _prepare_polygon(
    geometry: Union[Polygon, MultiPolygon], tolerance: float = 0.001
) -> str:
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


def _fetch_overpass_data(
    query: str, endpoint: str = "http://overpass-api.de/api/interpreter"
) -> list[dict[str, Any]]:
    """
    Send a GET request to Overpass API and return the elements list.
    Retries up to 3 times with exponential backoff on failure.
    """
    max_retries = 3
    backoff = 2  # seconds
    for attempt in range(max_retries):
        try:
            resp = requests.get(endpoint, params={"data": query}, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return data.get("elements", [])
        except (requests.exceptions.RequestException, ValueError) as e:
            if attempt < max_retries - 1:
                wait = backoff * (2 ** attempt)
                print(f"Overpass API error: {e}. Retrying in {wait} seconds...")
                time.sleep(wait)
            else:
                print(f"Overpass API error: {e}. No more retries left.")
                return []


def _build_node_index(elements: list[dict[str, Any]]) -> dict[int, tuple[float, float]]:
    """
    Create a mapping from node ID to (lon, lat) coordinates.
    """
    return {el["id"]: (el["lon"], el["lat"]) for el in elements if el["type"] == "node"}


def _extract_features(
    elements: list[dict[str, Any]], node_index: dict[int, tuple[float, float]]
) -> list[dict[str, Any]]:
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


def _build_gdf(
    features: list[dict[str, Any]], crs: str = "EPSG:4326"
) -> gpd.GeoDataFrame:
    """
    Construct a GeoDataFrame from a list of feature dicts.
    """
    if not features:
        # Return an empty GeoDataFrame with a geometry column and CRS
        return gpd.GeoDataFrame({'geometry': []}, geometry='geometry', crs=crs)
    return gpd.GeoDataFrame(features, crs=crs)


def query_overpass_candidates_inside_pc4_area(
    geometry: Union[Polygon, MultiPolygon],
    query_params: list[tuple[str, str]] = [("amenity", "parking")],
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


def calculate_ev_charging_density(geometry: Union[Polygon, MultiPolygon]) -> tuple[int, float]:
    """
    Calculate the number of EV charging stations and their density per km² in a given PC4 area.
    
    Args:
        geometry: A shapely Polygon or MultiPolygon representing the PC4 area
        
    Returns:
        tuple: (number_of_stations, density_per_km2)
    """
    query_params = [("amenity", "charging_station")]
    try:
        stations_gdf = query_overpass_candidates_inside_pc4_area(geometry, query_params)
        num_stations = len(stations_gdf)
    except Exception as e:
        print(f"Overpass API error: {e}")
        return None, None  # or (0, 0.0) if you prefer

    geo = gpd.GeoSeries([geometry], crs="EPSG:4326")
    area_km2 = geo.to_crs("EPSG:28992").area.iloc[0] / 1_000_000
    density = num_stations / area_km2 if area_km2 > 0 else 0
    return num_stations, density


def get_municipality_for_pc4(geometry: Union[Polygon, MultiPolygon], area_code: str) -> str:
    """
    Query OpenStreetMap to find the municipality that contains the given PC4 area.
    
    Args:
        geometry: A shapely Polygon or MultiPolygon representing the PC4 area
        
    Returns:
        str: The name of the municipality with the largest overlap
    """
    # Get sample points from across the geometry
    sample_points = _get_sample_points(geometry)
    
    # Try with multiple points and collect municipalities with their counts
    municipality_counts = {}
    
    for point in sample_points:
        lat, lon = point.y, point.x
        
        # Use a more reliable radius (100 meters instead of 1)
        query = f"""
        [out:json][timeout:60];
        relation["admin_level"="8"]["boundary"="administrative"](around:100,{lat},{lon});
        out tags;
        """
        
        elements = _fetch_overpass_data(query)
        
        for element in elements:
            tags = element.get('tags', {})
            if tags.get('boundary') == 'administrative' and tags.get('admin_level') == '8':
                name = tags.get('name:nl') or tags.get('name:en') or tags.get('name')
                if name:
                    municipality_counts[name] = municipality_counts.get(name, 0) + 1
    
    # No municipalities found
    if not municipality_counts:
        # Try with bounding box as a fallback
        minx, miny, maxx, maxy = geometry.bounds
        query = f"""
        [out:json][timeout:90];
        relation["admin_level"="8"]["boundary"="administrative"]({miny},{minx},{maxy},{maxx});
        out tags;
        """
        
        elements = _fetch_overpass_data(query)
        
        for element in elements:
            tags = element.get('tags', {})
            if tags.get('boundary') == 'administrative' and tags.get('admin_level') == '8':
                name = tags.get('name:nl') or tags.get('name:en') or tags.get('name')
                if name:
                    municipality_counts[name] = municipality_counts.get(name, 0) + 1
    
    # Still no municipalities found
    if not municipality_counts:
        #raise ValueError("No municipality found for the given PC4 area")
        print(f"No municipality found for the given PC4 area: {area_code}")
        return None
    
    # Return the municipality with the highest count
    return max(municipality_counts.items(), key=lambda x: x[1])[0]


def _get_sample_points(geometry: Union[Polygon, MultiPolygon], num_points: int = 5) -> list[Point]:
    """Generate sample points across the geometry."""
    points = []
    # Always include the centroid
    points.append(geometry.centroid)

    # Handle MultiPolygon vs Polygon
    if isinstance(geometry, MultiPolygon):
        polygons = list(geometry.geoms)
    else:
        polygons = [geometry]

    n_polygons = len(polygons)
    if n_polygons == 0:
        return points[:num_points]

    # If num_points < n_polygons, just sample the centroid of the first num_points polygons
    if num_points <= n_polygons:
        for poly in polygons[:num_points]:
            c = poly.centroid
            if c not in points:
                points.append(c)
        return points[:num_points]

    points_per_polygon = max(1, num_points // n_polygons)
    for polygon in polygons:
        x, y = polygon.exterior.coords.xy
        step = max(1, len(x) // points_per_polygon)
        for i in range(0, len(x), step):
            if len(points) < num_points:
                points.append(Point(x[i], y[i]))
        # If still need more points, try interior points
        if len(points) < num_points:
            minx, miny, maxx, maxy = polygon.bounds
            center_x = (minx + maxx) / 2
            center_y = (miny + maxy) / 2
            center = Point(center_x, center_y)
            if center.within(polygon) and center not in points:
                points.append(center)
    return points[:num_points]  # Cap at the requested number of points

