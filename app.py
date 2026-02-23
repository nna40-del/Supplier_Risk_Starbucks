import json

import streamlit as st


st.set_page_config(
    page_title="Supply Risk Scoring Intake",
    page_icon="📦",
    layout="centered",
)

st.title("Supply Risk Scoring Intake")
st.caption("Upload a JSON input file for the supply risk scoring workflow.")

st.markdown(
    """
Use this secure intake page to submit structured JSON data from your local machine.
After submission, the parsed payload is logged to the local Streamlit terminal.
"""
)

uploaded_file = st.file_uploader("Select a JSON file", type=["json"])

if uploaded_file is not None:
    st.write(f"Selected file: **{uploaded_file.name}**")

    if st.button("Submit JSON", type="primary"):
        try:
            parsed_json = json.load(uploaded_file)
            print("\n=== Supply Risk JSON Submission ===")
            print(f"Filename: {uploaded_file.name}")
            print(json.dumps(parsed_json, indent=2))
            print("=== End Submission ===\n")

            st.success("JSON submitted successfully. Check the local terminal for output.")
        except json.JSONDecodeError:
            st.error("Invalid JSON file. Please upload a valid .json document.")