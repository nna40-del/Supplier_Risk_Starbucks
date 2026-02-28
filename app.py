import json
import re
from typing import Any, Dict, List

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Import the news risk scoring module
from supplier_news_risk import score_article


st.set_page_config(
    page_title="Supply Risk Scoring Intake",
    page_icon="📦",
    layout="wide",
)

st.title("🚨 Supplier Risk Scoring & News Analysis")
st.caption("Upload JSON files with supplier data or paste news articles to assess supply chain risks.")

# Create tabs for different functionality
tab1, tab2 = st.tabs(["📊 Supplier Data Scoring", "📰 News Article Risk Assessment"])

# ============================================================================
# TAB 1: EXISTING SUPPLIER DATA SCORING
# ============================================================================
with tab1:
    st.markdown("### Upload Supplier JSON Data")
    st.markdown(
        """
Use this secure intake page to submit structured JSON data about your suppliers.
The system will score them based on food safety, regulatory, operational, and financial metrics.
"""
    )

    # Default scoring weights and thresholds
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
    default_cols = ["name", "risk_level", "risk_score", "risk_probability", "foodSafety", "regulatory", "operational", "financial"]
    col_order = default_cols

    uploaded_file = st.file_uploader("Select a JSON file", type=["json"], key="supplier_json")

    if uploaded_file is not None:
        st.write(f"Selected file: **{uploaded_file.name}**")

        if st.button("Submit JSON", type="primary", key="submit_supplier"):
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
                    if "no critical" in combined or "no major" in combined or "no enforcement" in combined:
                        score -= 0.15
                    return min(max(score, 0.0), 1.0)

                def score_regulatory(rc: Dict[str, Any]) -> float:
                    score = 0.5
                    combined = " ".join([str(v).lower() for v in rc.values()])
                    if any(x in combined for x in ("483", "open483", "observation", "observation", "warning")):
                        score += 0.35
                    if any(x in combined for x in ("no 483", "no 483s", "no enforcement", "clean")):
                        score -= 0.2
                    if "compliant" in combined or "verified" in combined or "signed" in combined:
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
                    if any(x in combined for x in ("backup", "redundancy", "identified", "multi-site", "multi")):
                        score -= 0.15
                    return min(max(score, 0.0), 1.0)

                def score_financial(fs_fin: Dict[str, Any]) -> float:
                    score = 0.5
                    combined = " ".join([str(v).lower() for v in fs_fin.values()])
                    if any(x in combined for x in ("low", "stable", "satisfactory", "strong", "audited")):
                        score -= 0.2
                    if any(x in combined for x in ("moderate", "moderately", "concentration", "seasonal", "private")):
                        score += 0.05
                    if any(x in combined for x in ("credit risk", "creditreview", "credit")) and "moderate" in combined:
                        score += 0.15
                    return min(max(score, 0.0), 1.0)

                def compute_supplier_risks(payload: Dict[str, Any], weights: Dict[str, float]) -> List[Dict[str, Any]]:
                    suppliers = payload.get("suppliers") or []
                    results = []
                    for s in suppliers:
                        fs = s.get("foodSafetyQuality", {})
                        rc = s.get("regulatoryCompliance", {})
                        op = s.get("operationalReliability", {})
                        fin = s.get("financialStability", {})

                        # use weights passed from UI (normalized)
                        total = weights.get("fs", 0) + weights.get("rc", 0) + weights.get("op", 0) + weights.get("fin", 0)
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

                        risk_probability = v_fs * w_fs + v_rc * w_rc + v_op * w_op + v_fin * w_fin
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

                st.success("✅ JSON submitted and scored successfully.")

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
                    row.update({
                        "foodSafety": subs.get("foodSafety"),
                        "regulatory": subs.get("regulatory"),
                        "operational": subs.get("operational"),
                        "financial": subs.get("financial"),
                    })
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
                st.markdown("### Risk Level Summary")
                c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
                counts = display_df["risk_level"].value_counts().to_dict()
                c1.metric("🟢 Low", counts.get("LOW", 0))
                c2.metric("🟡 Moderate", counts.get("MODERATE", 0))
                c3.metric("🔴 High", counts.get("HIGH", 0))
                c4.metric("⚫ Severe", counts.get("SEVERE", 0))

                avg_score = display_df["risk_score"].mean() if not display_df.empty else 0
                st.markdown(f"**Average risk score:** {avg_score:.1f} / 100")

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
                    gb.configure_column("risk_score", type=["numericColumn", "numberColumnFilter"], width=110)
                    gb.configure_column("risk_probability", type=["numericColumn"], width=130)
                    grid_options = gb.build()
                    AgGrid(display_df, gridOptions=grid_options, fit_columns_on_grid_load=True, enable_enterprise_modules=False, height=480)
                except Exception:
                    st.info("For an interactive table with sorting and filters, install `st-aggrid` (pip install st-aggrid). Showing static table instead.")
                    st.dataframe(df.style.format(fmt).bar(subset=["risk_score"], color="#f63366").hide(axis="index"), use_container_width=True, height=480)
                # Allow user to download scored results
                csv = display_df.to_csv(index=False)
                st.download_button("Download scored results (CSV)", csv, file_name="scored_suppliers.csv", mime="text/csv")
            except json.JSONDecodeError:
                st.error("❌ Invalid JSON file. Please upload a valid .json document.")


# ============================================================================
# TAB 2: NEWS ARTICLE RISK ASSESSMENT
# ============================================================================
with tab2:
    st.markdown("### 📰 Assess Supplier News Articles for Risk")
    st.markdown(
        """
Paste news articles or upload JSON files containing news text about your suppliers.
The AI will analyze them for labor violations, environmental damage, political instability, 
and financial distress, providing actionable risk scores and recommendations.
"""
    )

    # Risk level recommendations
    RISK_RECOMMENDATIONS = {
        "LOW": {
            "emoji": "🟢",
            "color": "#28a745",
            "description": "Low Risk",
            "recommendation": "✅ **Maintain current monitoring.** No immediate action required. Continue regular supplier audits.",
            "actions": [
                "• Monitor supplier quarterly",
                "• Keep existing contracts in place",
                "• No escalated action needed"
            ]
        },
        "MODERATE": {
            "emoji": "🟡",
            "color": "#ffc107",
            "description": "Moderate Risk",
            "recommendation": "⚠️ **Increase monitoring and communication.** Schedule a call with the supplier to discuss concerns.",
            "actions": [
                "• Request supplier response within 5 business days",
                "• Schedule management review call",
                "• Increase monitoring frequency to bi-weekly",
                "• Document all findings for audit trail"
            ]
        },
        "HIGH": {
            "emoji": "🔴",
            "color": "#fd7e14",
            "description": "High Risk",
            "recommendation": "🚨 **Escalate immediately.** Conduct an on-site inspection and consider contingency sourcing.",
            "actions": [
                "• Schedule urgent supplier meeting",
                "• Request detailed remediation plan",
                "• Consider on-site audit/inspection",
                "• Identify backup suppliers",
                "• Daily monitoring until resolved",
                "• Brief procurement team and leadership"
            ]
        },
        "SEVERE": {
            "emoji": "⚫",
            "color": "#dc3545",
            "description": "Severe Risk",
            "recommendation": "🛑 **CRITICAL - Take immediate action.** This supplier poses a critical threat to your supply chain.",
            "actions": [
                "• URGENT: Escalate to executive leadership",
                "• Activate business continuity plan",
                "• Initiate supplier contingency sourcing immediately",
                "• Cease non-emergency orders",
                "• Conduct legal/compliance review",
                "• Communicate with affected stakeholders",
                "• Real-time monitoring and daily reporting"
            ]
        }
    }

    # Two input methods: upload JSON or paste text
    input_method = st.radio("Choose input method:", ["📄 Paste News Article", "📁 Upload JSON File"])

    article_text = None

    if input_method == "📄 Paste News Article":
        st.markdown("#### Paste your news article below:")
        article_text = st.text_area(
            "News Article Content:",
            height=200,
            placeholder="Paste the full text of a news article about a supplier...",
            key="news_text"
        )
    else:
        uploaded_news_file = st.file_uploader("Upload a JSON file with news articles or supplier text", type=["json"], key="news_json")
        if uploaded_news_file is not None:
            try:
                news_data = json.load(uploaded_news_file)
                # Try to extract text from common JSON structures
                if isinstance(news_data, dict):
                    if "articles" in news_data and isinstance(news_data["articles"], list):
                        article_text = " ".join([str(a.get("text", a.get("content", ""))) for a in news_data["articles"]])
                    elif "text" in news_data:
                        article_text = news_data["text"]
                    elif "content" in news_data:
                        article_text = news_data["content"]
                    else:
                        article_text = json.dumps(news_data)
                elif isinstance(news_data, list):
                    article_text = " ".join([str(item) for item in news_data])
                else:
                    article_text = str(news_data)
            except json.JSONDecodeError:
                st.error("❌ Invalid JSON file format")

    if article_text and st.button("🔍 Analyze Article for Risk", type="primary", key="analyze_news"):
        if not article_text.strip():
            st.error("❌ Please provide article text to analyze")
        else:
            try:
                with st.spinner("🤖 AI is analyzing the article..."):
                    # Score the article
                    result = score_article(article_text)

                # Display main risk score prominently
                st.markdown("---")
                st.markdown("### 📊 Risk Assessment Results")

                # Determine risk level
                risk_score = result.overall_news_risk_score
                if risk_score <= 30:
                    risk_level = "LOW"
                elif risk_score <= 50:
                    risk_level = "MODERATE"
                elif risk_score <= 80:
                    risk_level = "HIGH"
                else:
                    risk_level = "SEVERE"

                rec = RISK_RECOMMENDATIONS[risk_level]

                # Main metric display
                col1, col2 = st.columns([2, 3])
                with col1:
                    st.metric(
                        "Overall Risk Score",
                        f"{risk_score:.1f}/100",
                        delta=None,
                        label_visibility="visible"
                    )
                with col2:
                    st.markdown(f"### {rec['emoji']} {rec['description']}")

                # Risk meter/gauge
                fig = go.Figure(go.Indicator(
                    mode="gauge+number+delta",
                    value=risk_score,
                    domain={'x': [0, 1], 'y': [0, 1]},
                    title={'text': "Risk Level"},
                    delta={'reference': 50},
                    gauge={
                        'axis': {'range': [None, 100]},
                        'bar': {'color': rec['color']},
                        'steps': [
                            {'range': [0, 30], 'color': "#d4edda"},
                            {'range': [30, 50], 'color': "#fff3cd"},
                            {'range': [50, 80], 'color': "#ffe5e5"},
                            {'range': [80, 100], 'color': "#f8d7da"}
                        ],
                        'threshold': {
                            'line': {'color': "red", 'width': 4},
                            'thickness': 0.75,
                            'value': 80}
                    }
                ))
                st.plotly_chart(fig, use_container_width=True)

                # Recommendation section
                st.markdown("---")
                st.markdown("### 📋 Recommendation")
                st.markdown(rec["recommendation"])
                
                st.markdown("#### Recommended Actions:")
                for action in rec["actions"]:
                    st.markdown(action)

                # Detailed scoring breakdown
                st.markdown("---")
                st.markdown("### 🔍 Detailed Analysis")

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    sentiment = result.sentiment_score
                    st.metric(
                        "Sentiment Score",
                        f"{sentiment:.3f}",
                        help="Range: -1 (very negative) to +1 (very positive). Negative sentiment = higher risk."
                    )
                with col2:
                    keyword_intensity = result.keyword_intensity_score
                    st.metric(
                        "Keyword Intensity",
                        f"{keyword_intensity:.3f}",
                        help="Frequency of risk keywords relative to article length. Higher = more risk signals."
                    )
                with col3:
                    disruption_sim = result.disruption_similarity_score
                    st.metric(
                        "Disruption Similarity",
                        f"{disruption_sim:.3f}",
                        help="How similar the article is to past supply chain crises. Higher = more concerning."
                    )
                with col4:
                    st.write("")  # spacer

                # Theme breakdown
                st.markdown("#### Risk Themes Detected:")
                themes = result.theme_scores
                theme_data = []
                for theme, score in themes.items():
                    theme_name = theme.replace("_", " ").title()
                    theme_data.append({"Theme": theme_name, "Score": score})

                theme_df = pd.DataFrame(theme_data)
                theme_df = theme_df.sort_values("Score", ascending=False).reset_index(drop=True)

                # Create a bar chart
                fig_themes = go.Figure(
                    go.Bar(
                        x=theme_df["Theme"],
                        y=theme_df["Score"],
                        marker_color=['#dc3545' if s > 0.05 else '#ffc107' if s > 0.02 else '#28a745' for s in theme_df["Score"]]
                    )
                )
                fig_themes.update_layout(
                    title="Risk Theme Intensity",
                    xaxis_title="Theme",
                    yaxis_title="Score",
                    height=400,
                    showlegend=False
                )
                st.plotly_chart(fig_themes, use_container_width=True)

                # Display as table
                st.dataframe(
                    theme_df.style.bar(subset=["Score"], color="#fd7e14"),
                    use_container_width=True,
                    hide_index=True
                )

                # Raw JSON output for technical review
                st.markdown("---")
                st.markdown("### 📄 Raw JSON Output")
                with st.expander("Click to expand raw results"):
                    st.json(result.to_dict())

                # Download results
                results_json = json.dumps({
                    "overall_risk_score": risk_score,
                    "risk_level": risk_level,
                    "recommendation": rec["recommendation"],
                    "detailed_results": result.to_dict()
                }, indent=2)
                st.download_button(
                    "📥 Download Assessment Results (JSON)",
                    results_json,
                    file_name="risk_assessment_results.json",
                    mime="application/json"
                )

            except Exception as e:
                st.error(f"❌ Error analyzing article: {str(e)}")
                with st.expander("Technical Details"):
                    st.write(str(e))
