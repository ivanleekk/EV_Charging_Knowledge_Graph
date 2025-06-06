import streamlit as st

st.title("Optimal new EV Charging Locations in Zuid-Holland")
st.subheader("2AMD20 Knowledge Engineering Group 7")

st.markdown(
    """
This project aims to identify optimal locations for new EV charging stations in Zuid-Holland, Netherlands, using Neo4j and Streamlit.
The project leverages Neo4j's graph database capabilities to analyze spatial relationships and Streamlit for interactive data visualization.
"""
)

st.write("Explore more with the views on the left sidebar:")
st.divider()

st.page_link(
    "./pages/Point Map View.py", label="Point Map View and Existing EV Chargers"
)
st.image(
    "./screenshots/point_map_view.png",
    caption="Point Map View Example",
    use_container_width=True,
)
st.image(
    "./screenshots/point_map_view_ev_charger.png",
    caption="Point Map View with Existing EV Chargers",
    use_container_width=True,
)

st.divider()
st.page_link("./pages/Score Map View.py", label="Score Map View (with Elevation)")
st.image(
    "./screenshots/score_map_view.png",
    caption="Score Map View Example",
    use_container_width=True,
)
st.divider()

st.page_link(
    "./pages/PC4 Map View.py", label="PC4 Map View (with Elevation and PC4 Information)"
)
st.image(
    "./screenshots/pc4_map_view.png",
    caption="PC4 Map View Example",
    use_container_width=True,
)
st.divider()

st.page_link(
    "./pages/Table View.py",
    label="Table View with detailed information on candidates and areas",
)
st.image(
    "./screenshots/table_view.png",
    caption="Table View Example",
    use_container_width=True,
)
st.divider()
st.page_link(
    "./pages/Rescoring.py", label="Rescore Candidates (Adjust Weights for Scoring)"
)
st.image(
    "./screenshots/rescore_view.png",
    caption="Rescore Candidates View Example",
    use_container_width=True,
)
