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
        id(c) AS CandidateId,
        c.location.latitude AS Latitude,
        c.location.longitude AS Longitude,
        c.nearest_location.latitude AS NearestLat,
        c.nearest_location.longitude AS NearestLon,
        c.distance_to_nearest AS DistanceToNearest,
        c.score AS Score,
        p.pc4_code AS PC4Code,
        m.name AS MunicipalityName
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
st.set_page_config(page_title="EV Candidate Locations Map", layout="wide")
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
deck = pdk.Deck(
    layers=[layer],
    initial_view_state=view_state,
    map_style="dark",
    tooltip={
        "text": "ID: {CandidateId}\nScore: {Score}\nDistance: {DistanceToNearest}\nPC4: {PC4Code}\nMunicipality: {MunicipalityName}"
    },
)
st.dataframe(df, use_container_width=True)


st.pydeck_chart(
    deck,
    use_container_width=True,
)

cid = st.selectbox(
    "Select a Candidate Location",
    options=df["CandidateId"].tolist(),
    index=0,
    key="candidate_select",
    help="Select a candidate location to view its details.",
)
charging_radius = st.slider(
    "Charging Station Radius (km)",
    min_value=1.0,
    max_value=100.0,
    value=1.0,
    step=0.25,
    help="Select the radius in kilometers to search for nearby charging stations.",
)

charging_limit = st.number_input(
    "Charging Stations Limit",
    min_value=1,
    max_value=1000,
    value=10,
    step=1,
    help="Limit the number of charging stations displayed on the map.",
)

# display a map of the selected candidate location with all charging stations nearby
if cid:
    selected_candidate = df[df["CandidateId"] == cid].iloc[0]

    def load_charging_stations():
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        query = f"""
        MATCH (a:EVChargingStation), (b:CandidateLocation)
        WHERE id(b) = {cid}
        MATCH (a:EVChargingStation), (b:CandidateLocation)
        WHERE point.distance(a.location, b.location) < {charging_radius} * 1000
        RETURN id(a) AS EVChargingStationID, id(b) AS CandidateLocationID, a.location as EVChargingStationLocation, point.distance(a.location, b.location)/1000 AS DistanceToCandidate 
        ORDER BY DistanceToCandidate ASC
        LIMIT {charging_limit}
        """
        with driver.session() as session:
            result = session.run(query, candidate_id=selected_candidate["CandidateId"])
            stations = pd.DataFrame([r.data() for r in result])
        driver.close()
        if stations.empty:
            return pd.DataFrame()
        return stations

    charging_stations = load_charging_stations()
    # convert each row from dictionary to a DataFrame row
    if isinstance(charging_stations, pd.Series):
        charging_stations = pd.DataFrame(charging_stations.tolist())

    if not charging_stations.empty:
        charging_stations["color"] = charging_stations.apply(
            lambda row: [0, 100, 255], axis=1
        )  # Blue color per row
        charging_stations["radius"] = charging_stations.apply(
            lambda row: 10, axis=1
        )  # Fixed radius per row
        st.dataframe(charging_stations, use_container_width=True)
        # add candidate location to the map
        candidate_location = {
            "EVChargingStationLocation": [
                selected_candidate["Longitude"],
                selected_candidate["Latitude"],
            ],
            "EVChargingStationID": selected_candidate["CandidateId"],
            "DistanceToCandidate": 0,  # Distance is zero for the candidate itself
            "color": [255, 0, 0],  # Red color for the candidate location
            "radius": 10,  # Fixed radius for the candidate location
        }

        charging_stations = pd.concat(
            [charging_stations, pd.DataFrame([candidate_location])], ignore_index=True
        )

        charging_layer = pdk.Layer(
            "ScatterplotLayer",
            data=charging_stations,
            get_position="EVChargingStationLocation",
            get_fill_color="color",
            radiusMinPixels=4,
            radiusMaxPixels=30,
            pickable=True,
            opacity=0.8,
        )

        charging_view_state = pdk.ViewState(
            latitude=selected_candidate["Latitude"],
            longitude=selected_candidate["Longitude"],
            zoom=10,
            pitch=0,
        )
        charging_deck = pdk.Deck(
            layers=[charging_layer],
            initial_view_state=charging_view_state,
            map_style="dark",
            tooltip={
                "text": "Charging Station: {EVChargingStationID}\nDistance: {DistanceToCandidate} km"
            },
        )
        st.pydeck_chart(
            charging_deck,
            use_container_width=True,
        )
    else:
        st.warning("No charging stations found within the selected radius.")
