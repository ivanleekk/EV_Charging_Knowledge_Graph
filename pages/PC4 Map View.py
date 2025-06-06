import streamlit as st
import pandas as pd
import pydeck as pdk
import shapely.wkt
from neo4j import GraphDatabase

# --- CONFIGURATION ---
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "12345678"


def load_data():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    query = """
    MATCH (c:CandidateLocation)-[]->(p:PC4Area)-[]->(m:Municipality)
    RETURN 
        AVG(c.score) AS AverageScore,
        AVG(c.location.latitude) AS AverageLatitude,
        AVG(c.location.longitude) AS AverageLongitude,
        COUNT(c) AS Count,
        p.pc4_code AS PC4Code,
        p.geometry AS PC4Geometry,
        m.name AS MunicipalityName
    """
    with driver.session() as session:
        result = session.run(query)
        df = pd.DataFrame([r.data() for r in result])
    driver.close()
    return df


df = load_data()
st.set_page_config(page_title="Average Score by PC4 Area", layout="wide")
st.header("🗺️ Average Score by PC4 Area")

# Calculate average score per PC4 area


# Parse WKT polygons into coordinates for PyDeck
def wkt_to_polygon_coords(wkt_str):
    if pd.isna(wkt_str):
        return None
    geom = shapely.wkt.loads(wkt_str)
    # Handles both Polygon and MultiPolygon
    if geom.geom_type == "Polygon":
        return [list(geom.exterior.coords)]
    elif geom.geom_type == "MultiPolygon":
        return [list(p.exterior.coords) for p in geom.geoms]
    else:
        return None


# --- COLOR FUNCTION ---
def score_to_color(score, min_score, max_score):
    norm_score = (score - min_score) / (max_score - min_score + 1e-5)
    r = int(180 * (1 - norm_score) ** 1.5)
    g = int(255 * norm_score**0.5)
    b = 30
    return [r, g, b]


min_avg, max_avg = df["AverageScore"].min(), df["AverageScore"].max()
df["color"] = df["AverageScore"].apply(lambda s: score_to_color(s, min_avg, max_avg))
df["Elevation"] = df["AverageScore"] / max_avg * 8000  # scale for 3D height

# Use WKT geometry for polygons
st.write(
    "PC4 Geometry WKT (Well-Known Text) format is used for polygon representation."
)
df["Polygon"] = df["PC4Geometry"].apply(wkt_to_polygon_coords)

pc4_view_state = pdk.ViewState(
    latitude=df["AverageLatitude"].mean(),
    longitude=df["AverageLongitude"].mean(),
    zoom=10,
    pitch=30,
)

pc4_polygon_layer = pdk.Layer(
    "PolygonLayer",
    data=df,
    get_polygon="Polygon",
    get_fill_color="color",
    get_elevation="Elevation",
    extruded=True,
    pickable=True,
    auto_highlight=True,
)


st.pydeck_chart(
    pdk.Deck(
        layers=[pc4_polygon_layer],
        initial_view_state=pc4_view_state,
        map_style="dark",
        tooltip={
            "text": "PC4: {PC4Code}\nMunicipality: {MunicipalityName}\nAvg Score: {AverageScore}\nCount: {Count}"
        },
    ),
    use_container_width=True,
)
