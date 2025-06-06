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

    RETURN c.location AS Location, c.score AS Score, c.distance_to_nearest AS DistanceToNearest, p.pc4_code AS PC4Code, p.density as ChargerDensity, m.name AS MunicipalityName, m.vehicles AS CarCount

    """
    with driver.session() as session:
        result = session.run(query)
        df = pd.DataFrame([r.data() for r in result])
    driver.close()
    return df


df = load_data()
unfiltered_df = df.copy()
# --- number input TO SELECT TOP N ---
st.set_page_config(page_title="Table View", layout="wide")
st.title("Optimal new EV Charging Locations in Zuid-Holland")
st.header("Best Locations for EV Charging Stations")
n = st.number_input(
    "Select number of top locations to show",
    min_value=10,
    max_value=len(df),
    value=50,
    step=10,
)

# --- FILTER TOP N LOCATIONS ---
df = df.sort_values(by="Score", ascending=False).head(n)


st.dataframe(df)

st.header("Number of Top Locations per Municipality")
top_locations_per_municipality = df["MunicipalityName"].value_counts().reset_index()
top_locations_per_municipality.columns = ["MunicipalityName", "TopLocationsCount"]
st.dataframe(top_locations_per_municipality)

st.header("Number of Top Locations per PC4 Area")
top_locations_per_pc4 = df["PC4Code"].value_counts().reset_index()
top_locations_per_pc4.columns = ["PC4Code", "TopLocationsCount"]
st.dataframe(top_locations_per_pc4)

st.header("Municipality Charging Stats")

# Group by municipality and compute required stats
municipality_stats = (
    unfiltered_df.groupby("MunicipalityName")
    .agg(
        ChargerCount=("MunicipalityName", "count"),  # count of rows = chargers
        TotalCars=("CarCount", "first"),  # assuming same value for all rows
        AvgDistanceToNearest=("DistanceToNearest", "mean"),  # average distance
        AvgScore=("Score", "mean"),  # average score
    )
    .reset_index()
)

# Compute chargers per 1000 cars
municipality_stats["ChargersPer1000Cars"] = (
    municipality_stats["ChargerCount"] / (municipality_stats["TotalCars"] + 1e-5) * 1000
)

# Display the DataFrame
st.dataframe(municipality_stats)
