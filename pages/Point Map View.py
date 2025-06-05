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
    MATCH (c:CandidateLocation) - [] -> (p:PC4Area) - [] -> (m:Municipality)

    RETURN c.lat AS Latitude, c.lon AS Longitude, c.score AS Score, c.distance_to_nearest AS DistanceToNearest, p.pc4_code AS PC4Code, m.name AS MunicipalityName
    """
    with driver.session() as session:
        result = session.run(query)
        df = pd.DataFrame([r.data() for r in result])
    driver.close()
    return df


df = load_data()


# --- COLOR MAPPING FUNCTION ---
def score_to_color(score):
    max_score = df["Score"].max()
    min_score = df["Score"].min()
    norm_score = (score - min_score) / (max_score - min_score + 1e-5)
    r = int(180 * (1 - norm_score) ** 1.5)
    g = int(255 * norm_score**0.5)
    b = 30
    return [r, g, b]


# --- DISPLAY IN STREAMLIT ---
st.title("EV Candidate Locations Map (Neo4j + PyDeck)")
# --- MUNICIPALITY FILTER ---
municipalities = ["All"] + sorted(df["MunicipalityName"].dropna().unique().tolist())
selected_municipalities = st.multiselect(
    "Filter by Municipality", sorted(df["MunicipalityName"].dropna().unique())
)

if selected_municipalities:
    df = df[df["MunicipalityName"].isin(selected_municipalities)]

# --- number input TO SELECT TOP N ---
n = st.number_input(
    "Select number of top locations to show",
    min_value=10,
    max_value=len(df),
    value=50,
    step=10,
)
# --- FILTER TOP N LOCATIONS ---
df = df.sort_values(by="Score", ascending=False).head(n)
df["color"] = df["Score"].apply(score_to_color)

# --- PYDECK SCATTERPLOT LAYER ---
layer = pdk.Layer(
    "ScatterplotLayer",
    data=df,
    get_position="[Longitude, Latitude]",
    get_fill_color="color",
    radiusMinPixels=4,  # minimum radius on screen
    radiusMaxPixels=30,  # maximum radius on screen
    pickable=True,
    opacity=0.8,
)


# --- VIEW STATE (CENTERED AUTOMATICALLY) ---
mid_lat = df["Latitude"].mean()
mid_lon = df["Longitude"].mean()

view_state = pdk.ViewState(latitude=mid_lat, longitude=mid_lon, zoom=10, pitch=0)


st.pydeck_chart(
    pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        map_style="dark",
        tooltip={
            "text": "Score: {Score}\nDistance: {DistanceToNearest}\nCoordinates: [{Longitude}, {Latitude}]\nPC4 Code: {PC4Code}\nMunicipality: {MunicipalityName}",
        },
    ),
    use_container_width=True,
)
