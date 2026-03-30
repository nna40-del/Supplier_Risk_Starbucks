import json
import re
from typing import Any, Dict, List

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


st.set_page_config(
    page_title="Supply Risk Scoring Intake",
    page_icon="📦",
    layout="wide",
)

st.title("Supply Risk Scoring Intake")
st.caption("Upload a JSON input file for the supply risk scoring workflow.")

st.markdown(
    """
Use this secure intake page to submit structured JSON data from your local machine.
After submission, the parsed payload is logged to the local Streamlit terminal.
"""
)

# Default scoring weights and thresholds (sidebar controls removed)
# Use sensible defaults so behavior is deterministic without UI controls
ws_fs = 35
ws_rc = 25
ws_op = 25
ws_fin = 15
# risk score thresholds for categorization
# low: 0-30, moderate: 31-50, high: 51-80, severe: 81-100
low_cut = 30
moderate_cut = 50
high_cut = 80

# Default column ordering
default_cols = [
    "name",
    "risk_level",
    "risk_score",
    "risk_probability",
    "foodSafety",
    "regulatory",
    "operational",
    "financial",
]
col_order = default_cols

uploaded_file = st.file_uploader("Select a JSON file", type=["json"])

if uploaded_file is not None:
    st.write(f"Selected file: **{uploaded_file.name}**")

    if st.button("Submit JSON", type="primary"):
        try:
            parsed_json = json.load(uploaded_file)

            def _parse_pct(s: Any) -> float:
                if s is None:
                    return 0.0
                if isinstance(s, (int, float)):
                    return float(s)
                s = str(s)
                m = re.search(r"(\d{1,3})(?:\.?\d*)%?", s)
                if m:
                    try:
                        return float(m.group(1))
                    except Exception:
                        return 0.0
                return 0.0

            def score_food_safety(fs: Dict[str, Any]) -> float:
                score = 0.5
                combined = " ".join([str(v).lower() for v in fs.values()])
                if "none" in combined and "recall" in combined:
                    score -= 0.35
                if "recall" in combined or "class" in combined:
                    score += 0.25
                if any(x in combined for x in ("sqf", "brcgs", "fssc", "gfs")):
                    score -= 0.2
                if (
                    "no critical" in combined
                    or "no major" in combined
                    or "no enforcement" in combined
                ):
                    score -= 0.15
                return min(max(score, 0.0), 1.0)

            def score_regulatory(rc: Dict[str, Any]) -> float:
                score = 0.5
                combined = " ".join([str(v).lower() for v in rc.values()])
                if any(
                    x in combined
                    for x in ("483", "open483", "observation", "observation", "warning")
                ):
                    score += 0.35
                if any(
                    x in combined
                    for x in ("no 483", "no 483s", "no enforcement", "clean")
                ):
                    score -= 0.2
                if (
                    "compliant" in combined
                    or "verified" in combined
                    or "signed" in combined
                ):
                    score -= 0.15
                return min(max(score, 0.0), 1.0)

            def score_operational(op: Dict[str, Any]) -> float:
                score = 0.5
                combined = " ".join([str(v).lower() for v in op.values()])
                otif = _parse_pct(op.get("otif", op.get("OTIF", "")))
                if otif:
                    if otif >= 97:
                        score -= 0.25
                    elif otif >= 94:
                        score -= 0.1
                    else:
                        score += 0.25
                lead = str(op.get("leadTime", "")).lower()
                if any(x in lead for x in ("10", "12", "14", "15", "long")):
                    score += 0.15
                if any(
                    x in combined
                    for x in (
                        "backup",
                        "redundancy",
                        "identified",
                        "multi-site",
                        "multi",
                    )
                ):
                    score -= 0.15
                return min(max(score, 0.0), 1.0)

            def score_financial(fs_fin: Dict[str, Any]) -> float:
                score = 0.5
                combined = " ".join([str(v).lower() for v in fs_fin.values()])
                if any(
                    x in combined
                    for x in ("low", "stable", "satisfactory", "strong", "audited")
                ):
                    score -= 0.2
                if any(
                    x in combined
                    for x in (
                        "moderate",
                        "moderately",
                        "concentration",
                        "seasonal",
                        "private",
                    )
                ):
                    score += 0.05
                if (
                    any(
                        x in combined for x in ("credit risk", "creditreview", "credit")
                    )
                    and "moderate" in combined
                ):
                    score += 0.15
                return min(max(score, 0.0), 1.0)

            def compute_supplier_risks(
                payload: Dict[str, Any], weights: Dict[str, float]
            ) -> List[Dict[str, Any]]:
                suppliers = payload.get("suppliers") or []
                results = []
                for s in suppliers:
                    fs = s.get("foodSafetyQuality", {})
                    rc = s.get("regulatoryCompliance", {})
                    op = s.get("operationalReliability", {})
                    fin = s.get("financialStability", {})

                    # use weights passed from UI (normalized)
                    total = (
                        weights.get("fs", 0)
                        + weights.get("rc", 0)
                        + weights.get("op", 0)
                        + weights.get("fin", 0)
                    )
                    if total <= 0:
                        w_fs = 0.35
                        w_rc = 0.25
                        w_op = 0.25
                        w_fin = 0.15
                    else:
                        w_fs = weights.get("fs", 0) / total
                        w_rc = weights.get("rc", 0) / total
                        w_op = weights.get("op", 0) / total
                        w_fin = weights.get("fin", 0) / total

                    v_fs = score_food_safety(fs)
                    v_rc = score_regulatory(rc)
                    v_op = score_operational(op)
                    v_fin = score_financial(fin)

                    risk_probability = (
                        v_fs * w_fs + v_rc * w_rc + v_op * w_op + v_fin * w_fin
                    )
                    risk_probability = min(max(risk_probability, 0.0), 1.0)
                    risk_score = int(round(risk_probability * 100))
                    # assign one of four risk levels based on configured thresholds
                    if risk_score <= low_cut:
                        risk_level = "LOW"
                    elif risk_score <= moderate_cut:
                        risk_level = "MODERATE"
                    elif risk_score <= high_cut:
                        risk_level = "HIGH"
                    else:
                        risk_level = "SEVERE"

                    result = {
                        "name": s.get("name"),
                        "risk_probability": round(risk_probability, 3),
                        "risk_score": risk_score,
                        "risk_level": risk_level,
                        "_subscores": {
                            "foodSafety": round(v_fs, 3),
                            "regulatory": round(v_rc, 3),
                            "operational": round(v_op, 3),
                            "financial": round(v_fin, 3),
                        },
                    }
                    results.append(result)
                return results

            weights = {"fs": ws_fs, "rc": ws_rc, "op": ws_op, "fin": ws_fin}
            scored = compute_supplier_risks(parsed_json, weights)

            print("\n=== Supply Risk JSON Submission (scored) ===")
            print(f"Filename: {uploaded_file.name}")
            print(json.dumps(scored, indent=2))
            print("=== End Submission ===\n")

            st.success("JSON submitted and scored successfully.")

            # Build a DataFrame and expand subscores into columns
            rows = []
            for r in scored:
                row = {
                    "name": r.get("name"),
                    "risk_level": r.get("risk_level"),
                    "risk_score": r.get("risk_score"),
                    "risk_probability": r.get("risk_probability"),
                }
                subs = r.get("_subscores", {})
                row.update(
                    {
                        "foodSafety": subs.get("foodSafety"),
                        "regulatory": subs.get("regulatory"),
                        "operational": subs.get("operational"),
                        "financial": subs.get("financial"),
                    }
                )
                rows.append(row)

            df = pd.DataFrame(rows)
            # Order columns for clarity
            # apply user column order preference, keep any missing columns appended
            ordered = [c for c in col_order if c in df.columns]
            remaining = [c for c in df.columns if c not in ordered]
            df = df[ordered + remaining]
            # remove default integer index so side numbers don't appear
            display_df = df.reset_index(drop=True)

            # Summary metrics (four categories)
            c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
            counts = display_df["risk_level"].value_counts().to_dict()
            c1.metric("Low", counts.get("LOW", 0))
            c2.metric("Moderate", counts.get("MODERATE", 0))
            c3.metric("High", counts.get("HIGH", 0))
            c4.metric("Severe", counts.get("SEVERE", 0))

            avg_score = display_df["risk_score"].mean() if not display_df.empty else 0
            st.markdown(f"**Average risk score:** {avg_score:.1f}")

            # Display an interactive table (AgGrid) if available, otherwise styled dataframe
            fmt = {
                "risk_probability": "{:.3f}",
                "risk_score": "{:.0f}",
                "foodSafety": "{:.3f}",
                "regulatory": "{:.3f}",
                "operational": "{:.3f}",
                "financial": "{:.3f}",
            }
            try:
                from st_aggrid import AgGrid
                from st_aggrid.grid_options_builder import GridOptionsBuilder

                gb = GridOptionsBuilder.from_dataframe(display_df)
                gb.configure_default_column(filter=True, sortable=True, resizable=True)
                gb.configure_column(
                    "risk_score",
                    type=["numericColumn", "numberColumnFilter"],
                    width=110,
                )
                gb.configure_column(
                    "risk_probability", type=["numericColumn"], width=130
                )
                grid_options = gb.build()
                AgGrid(
                    display_df,
                    gridOptions=grid_options,
                    fit_columns_on_grid_load=True,
                    enable_enterprise_modules=False,
                    height=480,
                )
            except Exception:
                st.info(
                    "For an interactive table with sorting and filters, install `st-aggrid` (pip install st-aggrid). Showing static table instead."
                )
                st.dataframe(
                    df.style.format(fmt)
                    .bar(subset=["risk_score"], color="#f63366")
                    .hide(axis="index"),
                    use_container_width=True,
                    height=480,
                )
            # Allow user to download scored results
            csv = display_df.to_csv(index=False)
            st.download_button(
                "Download scored results (CSV)",
                csv,
                file_name="scored_suppliers.csv",
                mime="text/csv",
            )
        except json.JSONDecodeError:
            st.error("Invalid JSON file. Please upload a valid .json document.")
