import streamlit as st
import pandas as pd
import pydeck as pdk
from neo4j import GraphDatabase

# --- CONFIGURATION ---
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "12345678"


# --- LOAD DATA FROM NEO4J ---
# @st.cache_data
def load_data():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    query = """
    MATCH (c:CandidateLocation)-[]->(p:PC4Area)-[]->(m:Municipality)
    RETURN 
        c.location.latitude AS Latitude,
        c.location.longitude AS Longitude,
        c.nearest_location.latitude AS NearestLat,
        c.nearest_location.longitude AS NearestLon,
        c.distance_to_nearest AS DistanceToNearest,
        c.score AS Score,
        p.pc4_code AS PC4Code,
        p.geometry AS PC4Geometry,
        m.name AS MunicipalityName
    """
    with driver.session() as session:
        result = session.run(query)
        df = pd.DataFrame([r.data() for r in result])
    driver.close()
    return df


# --- SQUARE AROUND EACH POINT ---
def square_around_point(lat, lon, size=0.0005):
    return [
        [lon - size, lat - size],
        [lon - size, lat + size],
        [lon + size, lat + size],
        [lon + size, lat - size],
        [lon - size, lat - size],
    ]


# --- COLOR FUNCTION ---
def score_to_color(score, min_score, max_score):
    norm_score = (score - min_score) / (max_score - min_score + 1e-5)
    r = int(180 * (1 - norm_score) ** 1.5)
    g = int(255 * norm_score**0.5)
    b = 30
    return [r, g, b]


# --- STREAMLIT UI ---
st.set_page_config(
    page_title="EV Candidate Locations Map with Elevation", layout="wide"
)
st.title("📍 EV Candidate Locations Map with Elevation (Neo4j + PyDeck)")

df = load_data()

# --- FILTER BY MUNICIPALITY ---
municipalities = sorted(df["MunicipalityName"].dropna().unique())
selected = st.multiselect("Filter by Municipality", municipalities)
if selected:
    df = df[df["MunicipalityName"].isin(selected)]

# --- TOP N SLIDER ---
n = st.number_input("Select number of top locations to show", 10, len(df), 50, 10)

df = df.sort_values(by="Score", ascending=False).head(n)
min_score, max_score = df["Score"].min(), df["Score"].max()

# --- ADD COLORS, POLYGONS, AND ELEVATIONS ---
df["color"] = df["Score"].apply(lambda s: score_to_color(s, min_score, max_score))
df["Polygon"] = df.apply(
    lambda row: square_around_point(row["Latitude"], row["Longitude"]), axis=1
)
df["Elevation"] = df["Score"] / max_score * 10000  # scale for 3D height

# --- VIEW STATE ---
mid_lat = df["Latitude"].mean()
mid_lon = df["Longitude"].mean()
view_state = pdk.ViewState(latitude=mid_lat, longitude=mid_lon, zoom=10, pitch=30)

# --- SCATTERPLOT LAYER ---
scatter_layer = pdk.Layer(
    "ScatterplotLayer",
    data=df,
    get_position="[Longitude, Latitude]",
    get_fill_color="color",
    get_radius=50,
    pickable=True,
    opacity=0.8,
)

# --- POLYGON LAYER (elevation based on score) ---
polygon_layer = pdk.Layer(
    "PolygonLayer",
    data=df,
    get_polygon="Polygon",
    get_fill_color="color",
    get_elevation="Elevation",
    extruded=True,
    pickable=True,
    auto_highlight=True,
)

# --- PYDECK CHART ---
st.pydeck_chart(
    pdk.Deck(
        layers=[polygon_layer, scatter_layer],
        initial_view_state=view_state,
        map_style="dark",
        tooltip={
            "text": "Score: {Score}\nDistance: {DistanceToNearest}\nPC4: {PC4Code}\nMunicipality: {MunicipalityName}"
        },
    ),
    use_container_width=True,
)
