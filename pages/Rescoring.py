import streamlit as st
from neo4j import GraphDatabase
from concurrent.futures import ThreadPoolExecutor
from itertools import islice
import numpy as np
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
URI = "bolt://localhost:7687"
AUTH = ("neo4j", "12345678")
BATCH_SIZE = 1000
MAX_THREADS = 8

driver = GraphDatabase.driver(URI, auth=AUTH)


def calculate_score(candidate, pc4, municipality):
    try:
        return (
            w1 * candidate["distance_to_nearest"]
            + w2 * (1 / (pc4["density"] + 1))
            + w3 * (municipality["home_value"] / 100000)
            + w4 * (municipality["vehicles"] / 1000)
            + w5 * (municipality["population_density"] / 1000)
        )
    except TypeError:
        return None


def batched(iterable, n):
    it = iter(iterable)
    while batch := list(islice(it, n)):
        yield batch


def process_municipality(municipality_name):
    start = time.perf_counter()
    all_candidates = []

    with driver.session() as session:
        result = session.run(
            """
            MATCH (c:CandidateLocation)-[:IS_LOCATED_IN]->(p:PC4Area)-[:IS_LOCATED_IN]->(m:Municipality {name: $municipality})
            RETURN properties(c) AS c, properties(p) AS p, properties(m) AS m
        """,
            municipality=municipality_name,
        )

        for record in result:
            c, p, m = record["c"], record["p"], record["m"]
            if not all([c, p, m]) or m.get("home_value") is None:
                continue
            score = calculate_score(c, p, m)
            if score is None:
                continue
            c["score"] = score
            all_candidates.append(c)

    # Write scores back to Neo4j
    with driver.session() as session:
        for batch in batched(all_candidates, BATCH_SIZE):
            session.run(
                """
                UNWIND $candidates AS candidate
                MATCH (c:CandidateLocation {lon: candidate.lon, lat: candidate.lat})
                SET c.score = candidate.score
            """,
                candidates=batch,
            )
    print(
        f"[{municipality_name}] Scored {len(all_candidates)} candidates in {time.perf_counter() - start:.2f}s."
    )


# --- STREAMLIT PAGE ---
st.set_page_config(page_title="Rescore Candidates", layout="wide")
st.title("🔧 Rescore EV Candidate Locations")

with st.form("weight_form"):
    st.subheader("Adjust Weights")
    w1 = st.slider("Closest Charging Location", 0.0, 10.0, 3.0, 0.1)
    w2 = st.slider("EV Charger Density", 0.0, 10.0, 5.0, 0.1)
    w3 = st.slider("Average Home Value", 0.0, 10.0, 0.5, 0.1)
    w4 = st.slider("Number of Vehicles", 0.0, 10.0, 2.0, 0.1)
    w5 = st.slider("Population Density", 0.0, 10.0, 1.0, 0.1)

    submitted = st.form_submit_button("Rescore All Municipalities")

if submitted:
    weights = {
        "closest_charging_location": w1,
        "ev_charger_density": w2,
        "avg_home_value": w3,
        "number_of_vehicles": w4,
        "population_density": w5,
    }

    st.success("Started scoring. This might take a while...")
    st.warning(
        "Please do not close the browser or change pages until the process is complete!"
    )
    start_time = time.perf_counter()

    with driver.session() as session:
        result = session.run("MATCH (m:Municipality) RETURN m.name AS name")
        municipalities = [r["name"] for r in result]

    # working
    # results = []
    # with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
    #     executor.map(process_municipality, municipalities)

    # Display progress bar after rescoring
    progress_bar = st.progress(0)
    total = len(municipalities)
    completed = 0

    results = []
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        futures = {executor.submit(process_municipality, m): m for m in municipalities}
        for future in as_completed(futures):
            completed += 1
            progress_bar.progress(completed / total)
            # Optionally, collect results if process_municipality returns a value
            # results.append(future.result())

    progress_bar.empty()

    st.success(
        f"✅ Done! Updated candidates in {time.perf_counter() - start_time:.2f} seconds."
    )
