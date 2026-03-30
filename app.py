import json
import re
from typing import Any, Dict, List

import io
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Import the news risk scoring module
from supplier_news_risk import score_article
from database import SupplierDatabase
from news_database import NewsDatabase

# optional PDF support
try:
    import PyPDF2
except Exception:  # pragma: no cover - optional dependency
    PyPDF2 = None

# Initialize session state for data refresh tracking
if 'last_update' not in st.session_state:
    st.session_state.last_update = None
if 'data_refresh_trigger' not in st.session_state:
    st.session_state.data_refresh_trigger = 0


st.set_page_config(
    page_title="Supply Risk Scoring Intake",
    page_icon="📦",
    layout="wide",
)

st.title("🚨 Supplier Risk Scoring & News Analysis")
st.caption("Manage supplier data and news articles in one unified platform for supply chain risk assessment.")

# Create two sections for Supplier Scoring and News Analysis
supplier_expander = st.expander("📊 Upload & Score Supplier Data", expanded=True)
news_expander = st.expander("📰 Upload & Analyze News Articles", expanded=False)

# ============================================================================
# SUPPLIER DATA SCORING SECTION
# ============================================================================
with supplier_expander:
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

                # ===================================================================
                # SAVE TO DATABASE
                # ===================================================================
                db = SupplierDatabase()
                suppliers_list = parsed_json.get("suppliers", [])
                
                saved_count = 0
                for i, supplier in enumerate(suppliers_list):
                    try:
                        # Save supplier to database
                        supplier_id = db.save_supplier(supplier)
                        
                        # Find corresponding scoring result
                        scored_result = scored[i] if i < len(scored) else None
                        if scored_result and supplier_id:
                            # Save scoring result
                            db.save_scoring_result(
                                supplier_id=supplier_id,
                                risk_score=scored_result.get("risk_score", 0),
                                risk_level=scored_result.get("risk_level", "UNKNOWN"),
                                subscores=scored_result.get("_subscores", {})
                            )
                            saved_count += 1
                    except Exception as e:
                        print(f"Error saving supplier {supplier.get('name')}: {str(e)}")
                
                st.success(f"✅ JSON submitted and scored successfully. **{saved_count} suppliers saved to database.**")
                
                # Update session state to trigger combined insights refresh
                import datetime
                st.session_state.last_update = datetime.datetime.now()
                st.session_state.data_refresh_trigger += 1

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

                # ===================================================================
                # VISUALIZATIONS FOR DETAILED BREAKDOWN
                # ===================================================================
                st.markdown("---")
                st.markdown("### 📊 Detailed Risk Breakdown Charts")
                
                # Create tabs for different visualization options
                viz_tab1, viz_tab2, viz_tab3 = st.tabs(["📈 Component Scores by Supplier", "🎯 Individual Supplier Details", "📋 Risk Profile Comparison"])
                
                with viz_tab1:
                    # Bar chart showing all components for each supplier
                    chart_data = display_df[["name", "risk_probability", "foodSafety", "regulatory", "operational", "financial"]].copy()
                    chart_data_melted = chart_data.melt(id_vars=["name"], var_name="Risk Component", value_name="Score")
                    
                    fig = go.Figure()
                    for component in ["risk_probability", "foodSafety", "regulatory", "operational", "financial"]:
                        component_data = chart_data[chart_data.columns[0:1].tolist() + [component]]
                        component_label = component.replace("_", " ").title() if component != "risk_probability" else "Overall Risk Probability"
                        fig.add_trace(go.Bar(
                            name=component_label,
                            x=chart_data["name"],
                            y=chart_data[component],
                            text=[f"{v:.2f}" for v in chart_data[component]],
                            textposition="auto",
                        ))
                    
                    fig.update_layout(
                        title="Risk Component Scores by Supplier",
                        xaxis_title="Supplier Name",
                        yaxis_title="Score (0.0 - 1.0 for components, varies for overall)",
                        barmode="group",
                        height=500,
                        hovermode="x unified"
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    
                    st.caption("📌 **Note**: Overall Risk Probability combines all component scores with configured weights. Individual components (Food Safety, Regulatory, Operational, Financial) show their individual risk scores.")

                with viz_tab2:
                    # Detailed breakdown for each supplier with radar chart
                    if len(display_df) > 0:
                        selected_supplier = st.selectbox(
                            "Select a supplier to view detailed risk profile:",
                            display_df["name"].tolist(),
                            key="supplier_detail_select"
                        )
                        
                        supplier_row = display_df[display_df["name"] == selected_supplier].iloc[0]
                        
                        # Create vertical card layout with all details
                        st.subheading(f"📋 Detailed Profile: {selected_supplier}")
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("🎯 Overall Risk Score", f"{supplier_row['risk_score']}", 
                                     delta=f"Probability: {supplier_row['risk_probability']:.3f}")
                        with col2:
                            st.metric("⚠️ Risk Level", supplier_row['risk_level'])
                        with col3:
                            st.metric("📊 Risk Probability", f"{supplier_row['risk_probability']:.3f}")
                        
                        # Component breakdown with color coding
                        comp_col1, comp_col2, comp_col3, comp_col4 = st.columns(4)
                        
                        # Color coding based on score (lower = better)
                        def get_color(score):
                            if score <= 0.3:
                                return "🟢"
                            elif score <= 0.5:
                                return "🟡"
                            elif score <= 0.8:
                                return "🔴"
                            else:
                                return "⚫"
                        
                        with comp_col1:
                            fs_score = supplier_row['foodSafety']
                            st.metric(f"{get_color(fs_score)} Food Safety", f"{fs_score:.3f}")
                        with comp_col2:
                            reg_score = supplier_row['regulatory']
                            st.metric(f"{get_color(reg_score)} Regulatory", f"{reg_score:.3f}")
                        with comp_col3:
                            op_score = supplier_row['operational']
                            st.metric(f"{get_color(op_score)} Operational", f"{op_score:.3f}")
                        with comp_col4:
                            fin_score = supplier_row['financial']
                            st.metric(f"{get_color(fin_score)} Financial", f"{fin_score:.3f}")
                        
                        # Radar chart for this supplier
                        categories = ['Food Safety', 'Regulatory', 'Operational', 'Financial', 'Overall Risk Probability']
                        values = [
                            supplier_row['foodSafety'],
                            supplier_row['regulatory'],
                            supplier_row['operational'],
                            supplier_row['financial'],
                            supplier_row['risk_probability']
                        ]
                        
                        fig_radar = go.Figure(data=go.Scatterpolar(
                            r=values,
                            theta=categories,
                            fill='toself',
                            name=selected_supplier,
                            line_color='#636EFA'
                        ))
                        
                        fig_radar.update_layout(
                            polar=dict(
                                radialaxis=dict(
                                    visible=True,
                                    range=[0, 1],
                                    tickfont=dict(size=10)
                                ),
                                bgcolor="rgba(240, 240, 240, 0.5)"
                            ),
                            title=f"Risk Profile Radar: {selected_supplier}",
                            height=500,
                            showlegend=True
                        )
                        
                        st.plotly_chart(fig_radar, use_container_width=True)

                with viz_tab3:
                    # Heatmap-style comparison of all suppliers
                    heatmap_data = display_df[["name", "risk_probability", "foodSafety", "regulatory", "operational", "financial"]].copy()
                    heatmap_data.columns = ["Supplier", "Overall Risk\nProbability", "Food\nSafety", "Regulatory", "Operational", "Financial"]
                    
                    fig_heatmap = go.Figure(data=go.Heatmap(
                        z=heatmap_data[["Overall Risk\nProbability", "Food\nSafety", "Regulatory", "Operational", "Financial"]].values,
                        x=["Overall Risk\nProbability", "Food\nSafety", "Regulatory", "Operational", "Financial"],
                        y=heatmap_data["Supplier"],
                        colorscale="RdYlGn_r",
                        text=heatmap_data[["Overall Risk\nProbability", "Food\nSafety", "Regulatory", "Operational", "Financial"]].round(3).values,
                        texttemplate="%{text:.3f}",
                        textfont={"size": 12},
                        hovertemplate="<b>%{y}</b><br>%{x}: %{z:.3f}<extra></extra>"
                    ))
                    
                    fig_heatmap.update_layout(
                        title="Risk Profile Heatmap - All Suppliers",
                        xaxis_title="Risk Component",
                        yaxis_title="Supplier",
                        height=max(300, 50 * len(display_df)),
                    )
                    
                    st.plotly_chart(fig_heatmap, use_container_width=True)
                    st.caption("🟢 Green = Lower Risk | 🟡 Yellow = Moderate Risk | 🔴 Red = Higher Risk")

                # Allow user to download scored results
                csv = display_df.to_csv(index=False)
                st.download_button("Download scored results (CSV)", csv, file_name="scored_suppliers.csv", mime="text/csv")
            except json.JSONDecodeError:
                st.error("❌ Invalid JSON file. Please upload a valid .json document.")

# ============================================================================
# NEWS ARTICLE RISK ASSESSMENT SECTION
# ============================================================================
with news_expander:
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

    # Two input methods: paste text, upload JSON or TXT files
    input_method = st.radio("Choose input method:", ["📄 Paste News Article", "📁 Upload File (JSON or TXT)"])

    articles_list: List[Dict[str, Any]] = []

    if input_method == "📄 Paste News Article":
        st.markdown("#### Paste your news article below:")
        txt = st.text_area(
            "News Article Content:",
            height=200,
            placeholder="Paste the full text of a news article about a supplier...",
            key="news_text"
        )
        if txt and txt.strip():
            articles_list = [{"id": 0, "text": txt.strip()}]
    else:
        uploaded_news_files = st.file_uploader("Upload file(s) with news articles (JSON, TXT, or PDF)", type=["json", "txt", "pdf"], accept_multiple_files=True, key="news_json")
        if uploaded_news_files:
            for uploaded_news_file in uploaded_news_files:
                try:
                    name = uploaded_news_file.name or "uploaded"
                    content_bytes = uploaded_news_file.read()
                    # handle PDF files explicitly
                    processed = False
                    if name.lower().endswith(".pdf"):
                        if PyPDF2 is None:
                            st.error("PDF support requires PyPDF2. Install it with `pip install PyPDF2`.")
                            processed = True
                        else:
                            try:
                                reader = PyPDF2.PdfReader(io.BytesIO(content_bytes))
                                pages = []
                                for p in reader.pages:
                                    page_text = p.extract_text() or ""
                                    pages.append(page_text)
                                text = "\n".join(pages)
                                paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
                                for i, p in enumerate(paragraphs):
                                    articles_list.append({"id": len(articles_list), "text": p, "filename": name})
                                processed = True
                            except Exception:
                                st.error(f"Failed to parse PDF content for {name}.")
                                processed = True

                    # try JSON first (unless PDF already processed)
                    if not processed:
                        try:
                            news_data = json.loads(content_bytes.decode("utf-8"))
                        except Exception:
                            # treat as plain text file; split into paragraphs by blank lines
                            try:
                                text = content_bytes.decode("utf-8")
                            except Exception:
                                text = content_bytes.decode("latin-1")
                            paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
                            for i, p in enumerate(paragraphs):
                                articles_list.append({"id": len(articles_list), "text": p, "filename": name})
                        else:
                            # normalize to list of article texts
                            if isinstance(news_data, dict):
                                if "articles" in news_data and isinstance(news_data["articles"], list):
                                    for i, a in enumerate(news_data["articles"]):
                                        if isinstance(a, dict):
                                            text = a.get("text", a.get("content", json.dumps(a)))
                                        else:
                                            text = str(a)
                                        if text and str(text).strip():
                                            articles_list.append({"id": len(articles_list), "text": str(text).strip(), "filename": name})
                                elif "text" in news_data:
                                    text = news_data["text"]
                                    articles_list.append({"id": len(articles_list), "text": str(text).strip(), "filename": name})
                                elif "content" in news_data:
                                    text = news_data["content"]
                                    articles_list.append({"id": len(articles_list), "text": str(text).strip(), "filename": name})
                                else:
                                    # fallback: stringify and treat as single article
                                    articles_list.append({"id": len(articles_list), "text": json.dumps(news_data), "filename": name})
                            elif isinstance(news_data, list):
                                for i, item in enumerate(news_data):
                                    if isinstance(item, dict):
                                        text = item.get("text", item.get("content", json.dumps(item)))
                                    else:
                                        text = str(item)
                                    if text and str(text).strip():
                                        articles_list.append({"id": len(articles_list), "text": str(text).strip(), "filename": name})
                            else:
                                articles_list.append({"id": len(articles_list), "text": str(news_data), "filename": name})
                except Exception:
                    st.error(f"❌ Invalid or unreadable file format for {uploaded_news_file.name}")
            if articles_list:
                st.success(f"Loaded {len(articles_list)} article(s) from {len(uploaded_news_files)} file(s).")

    if articles_list and st.button("🔍 Analyze Article(s) for Risk", type="primary", key="analyze_news"):
        try:
            with st.spinner("🤖 AI is analyzing the article(s)..."):
                # Initialize news database
                news_db = NewsDatabase()
                # also load supplier names for matching
                sup_db = SupplierDatabase()
                supplier_names = [s.get("name") for s in sup_db.get_all_suppliers() if s.get("name")]
                
                # Score each article and collect results
                batch_results: List[Dict[str, Any]] = []
                for entry in articles_list:
                    text = entry.get("text", "")
                    if not text or not str(text).strip():
                        continue
                    res = score_article(text)
                    score_val = res.overall_news_risk_score
                    if score_val <= 30:
                        level = "LOW"
                    elif score_val <= 50:
                        level = "MODERATE"
                    elif score_val <= 80:
                        level = "HIGH"
                    else:
                        level = "SEVERE"
                    rec = RISK_RECOMMENDATIONS[level]
                    batch_results.append({
                        "id": entry.get("id"),
                        "excerpt": (text[:120] + "...") if len(text) > 120 else text,
                        "overall_risk_score": score_val,
                        "risk_level": level,
                        "recommendation": rec["recommendation"],
                        "sentiment_score": res.sentiment_score,
                        "keyword_intensity_score": res.keyword_intensity_score,
                        "disruption_similarity_score": res.disruption_similarity_score,
                        "theme_scores": res.theme_scores,
                        "raw_results": res.to_dict(),
                        "article_text": text,  # Store original text for database
                        "filename": entry.get("filename", "pasted_text.txt"),
                    })

                # ===================================================================
                # SAVE TO NEWS DATABASE
                # ===================================================================
                saved_count = 0
                for i, result in enumerate(batch_results):
                    try:
                        # Generate filename if not from file upload
                        filename = result.get("filename", f"news_article_{i+1}.txt") if input_method == "📄 Paste News Article" else result.get("filename", f"news_article_{i+1}.txt")
                        
                        # determine supplier name(s) referenced in article text
                        supplier_match = None
                        def normalize_text(text):
                            """Normalize text for better matching by removing punctuation and extra spaces."""
                            import re
                            # Remove apostrophes (both straight and curly), quotes, and other punctuation
                            text = re.sub(r"[\'\u2019\"]", "", text)
                            # Remove extra spaces
                            text = re.sub(r"\s+", " ", text).strip()
                            return text.lower()
                        
                        article_text_normalized = normalize_text(result["article_text"])
                        for name in supplier_names:
                            if name:
                                name_normalized = normalize_text(name)
                                # Check if normalized supplier name is in normalized article text
                                if name_normalized in article_text_normalized:
                                    supplier_match = name
                                    break
                                # Also try partial matches (e.g., "diana bakery" should match "diana's bakery")
                                name_parts = name_normalized.split()
                                if len(name_parts) > 1:
                                    # Check if major parts of the name are present
                                    major_parts = [part for part in name_parts if len(part) > 2]  # Skip short words
                                    if all(part in article_text_normalized for part in major_parts[:2]):  # Match first 2 major parts
                                        supplier_match = name
                                        break
                        # no match found in paragraph text? try filename fallback
                        if supplier_match is None:
                            fname_norm = normalize_text(filename or "")
                            for name in supplier_names:
                                if name:
                                    name_norm = normalize_text(name)
                                    if name_norm in fname_norm:
                                        supplier_match = name
                                        break
                        
                        # Save article to database with optional supplier linkage
                        article_id = news_db.save_article(filename, result["article_text"], supplier_name=supplier_match)
                        
                        # Save scoring result
                        if article_id:
                            news_db.save_scoring_result(
                                article_id=article_id,
                                overall_risk_score=result["overall_risk_score"],
                                risk_level=result["risk_level"],
                                sentiment_score=result["sentiment_score"],
                                keyword_intensity_score=result["keyword_intensity_score"],
                                disruption_similarity_score=result["disruption_similarity_score"],
                                theme_scores=result["theme_scores"],
                                full_results=result["raw_results"]
                            )
                            saved_count += 1
                    except Exception as e:
                        print(f"Error saving article to database: {str(e)}")
                
                if saved_count > 0:
                    st.success(f"✅ Analysis complete. **{saved_count} article(s) saved to database.**")
                    # Update session state to trigger combined insights refresh
                    import datetime
                    st.session_state.last_update = datetime.datetime.now()
                    st.session_state.data_refresh_trigger += 1

                # If multiple articles, show a batch table; if only one, show detailed view
                if len(batch_results) == 0:
                    st.warning("No valid articles found to analyze.")
                elif len(batch_results) == 1:
                    single = batch_results[0]
                    res = single["raw_results"]
                    risk_score = single["overall_risk_score"]
                    risk_level = single["risk_level"]
                    rec = RISK_RECOMMENDATIONS[risk_level]

                    st.markdown("---")
                    st.markdown("### 📊 Risk Assessment Results")
                    col1, col2 = st.columns([2, 3])
                    with col1:
                        st.metric("Overall Risk Score", f"{risk_score:.1f}/100")
                    with col2:
                        st.markdown(f"### {rec['emoji']} {rec['description']}")

                    # show same detailed breakdown as before
                    st.markdown("### 🔍 Detailed Analysis")
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Sentiment Score", f"{res['sentiment_score']:.3f}")
                    with col2:
                        st.metric("Keyword Intensity", f"{res['keyword_intensity_score']:.3f}")
                    with col3:
                        st.metric("Disruption Similarity", f"{res['disruption_similarity_score']:.3f}")

                    theme_df = pd.DataFrame([{"Theme": k.replace("_", " ").title(), "Score": v} for k, v in res['theme_scores'].items()])
                    theme_df = theme_df.sort_values("Score", ascending=False).reset_index(drop=True)
                    st.plotly_chart(go.Figure(go.Bar(x=theme_df['Theme'], y=theme_df['Score'])), use_container_width=True)
                    st.dataframe(theme_df.style.bar(subset=["Score"], color="#fd7e14"), use_container_width=True, hide_index=True)

                    st.markdown("### 📄 Raw JSON Output")
                    with st.expander("Click to expand raw results"):
                        st.json(res)

                    st.download_button("📥 Download Assessment Results (JSON)", json.dumps(single, indent=2), file_name="risk_assessment_single.json", mime="application/json")
                else:
                    # Build a DataFrame for batch results
                    df_batch = pd.DataFrame([{k: v for k, v in r.items() if k not in ("raw_results", "theme_scores", "article_text")} for r in batch_results])
                    st.markdown("---")
                    st.markdown(f"### 📊 Batch Results — {len(batch_results)} articles analyzed")
                    try:
                        from st_aggrid import AgGrid
                        from st_aggrid.grid_options_builder import GridOptionsBuilder
                        gb = GridOptionsBuilder.from_dataframe(df_batch)
                        gb.configure_default_column(filter=True, sortable=True, resizable=True)
                        AgGrid(df_batch, fit_columns_on_grid_load=True, enable_enterprise_modules=False, height=400)
                    except Exception:
                        st.dataframe(df_batch, use_container_width=True)

                    # Provide downloads
                    st.download_button("📥 Download Batch Results (JSON)", json.dumps(batch_results, indent=2), file_name="risk_assessment_batch.json", mime="application/json")
                    st.download_button("📥 Download Batch Results (CSV)", df_batch.to_csv(index=False), file_name="risk_assessment_batch.csv", mime="text/csv")

        except Exception as e:
            st.error(f"❌ Error analyzing article(s): {str(e)}")
            with st.expander("Technical Details"):
                st.write(str(e))

# ============================================================================
# COMBINED DATABASE MANAGEMENT SECTION
# ============================================================================
st.markdown("---")

db_tabs = st.tabs(["🧩 Combined Insights"])

with db_tabs[0]:
    st.markdown("### 🧩 Combined Supplier/News Insights")
    
    # Add refresh button and last update info
    col1, col2 = st.columns([3, 1])
    with col1:
        if st.session_state.last_update:
            # Check if update was recent (within last 30 seconds)
            import datetime
            time_diff = datetime.datetime.now() - st.session_state.last_update
            if time_diff.total_seconds() < 30:
                st.success(f"✅ Data updated: {st.session_state.last_update.strftime('%H:%M:%S')}")
            else:
                st.info(f"📅 Last updated: {st.session_state.last_update.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            st.info("📅 No data updates yet")
    with col2:
        if st.button("🔄 Refresh Data", key="refresh_combined_data"):
            st.session_state.data_refresh_trigger += 1
            st.rerun()
    
    # initialize databases
    db = SupplierDatabase()
    news_db = NewsDatabase()
    
    # Display database statistics
    all_suppliers = db.get_all_suppliers()
    news_stats = news_db.get_supplier_news_stats()

    # build combined summary records
    combined_data = []
    for s in all_suppliers:
        name = s.get("name")
        count = news_stats.get(name, {}).get("count", 0)
        avg_news = news_stats.get(name, {}).get("avg_score", 0)
        max_news = news_stats.get(name, {}).get("max_score", 0)
        combined_score = None
        combined_level = None
        if count > 0:
            # scale both scores 0-100 and average them
            combined_score = round((s.get("risk_score", 0) + avg_news) / 2, 1)
            if combined_score <= low_cut:
                combined_level = "LOW"
            elif combined_score <= moderate_cut:
                combined_level = "MODERATE"
            elif combined_score <= high_cut:
                combined_level = "HIGH"
            else:
                combined_level = "SEVERE"

        combined_data.append({
            "Name": name,
            "Risk Probability": s.get("risk_probability"),
            "Food Safety": s.get("foodSafety"),
            "Regulatory": s.get("regulatory"),
            "Operational": s.get("operational"),
            "Financial": s.get("financial"),
            "Supplier Risk Score": s.get("risk_score"),
            "Supplier Risk Level": s.get("risk_level"),
            "Articles": count,
            "Avg News Risk": round(avg_news, 1),
            "Max News Risk": round(max_news, 1),
            "Combined Score": combined_score if combined_score is not None else "N/A",
            "Combined Level": combined_level if combined_level is not None else "N/A",
        })

    if combined_data:
        combined_df = pd.DataFrame(combined_data)

        # summary metrics
        total_with_news = int((combined_df["Articles"] > 0).sum())
        avg_combined = None
        if total_with_news > 0:
            avg_combined = combined_df.loc[combined_df["Articles"] > 0, "Combined Score"].astype(float).mean()
        col1, col2 = st.columns(2)
        col1.metric("🔗 Suppliers w/ News", total_with_news)
        if avg_combined is not None:
            col2.metric("📉 Avg Combined Score", f"{avg_combined:.1f}")
        else:
            col2.metric("📉 Avg Combined Score", "N/A")

        st.dataframe(combined_df, use_container_width=True)

        # chart supplier risk vs news risk with component breakdown
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name="Risk Probability",
            x=combined_df["Name"],
            y=combined_df["Risk Probability"],
        ))
        fig.add_trace(go.Bar(
            name="Food Safety",
            x=combined_df["Name"],
            y=combined_df["Food Safety"],
        ))
        fig.add_trace(go.Bar(
            name="Regulatory",
            x=combined_df["Name"],
            y=combined_df["Regulatory"],
        ))
        fig.add_trace(go.Bar(
            name="Operational",
            x=combined_df["Name"],
            y=combined_df["Operational"],
        ))
        fig.add_trace(go.Bar(
            name="Financial",
            x=combined_df["Name"],
            y=combined_df["Financial"],
        ))
        fig.add_trace(go.Bar(
            name="Supplier Risk Score",
            x=combined_df["Name"],
            y=combined_df["Supplier Risk Score"],
        ))
        fig.add_trace(go.Bar(
            name="Avg News Risk",
            x=combined_df["Name"],
            y=combined_df["Avg News Risk"],
        ))
        fig.update_layout(barmode="group", xaxis_tickangle=-45, height=500)
        st.plotly_chart(fig, use_container_width=True)

        # allow inspection of individual supplier's articles
        if total_with_news > 0:
            st.subheader("🔍 Drill into supplier details")
            selected_supplier = st.selectbox(
                "Choose a supplier to view linked news articles:",
                combined_df["Name"],
                key="combined_supplier_select"
            )
            if selected_supplier:
                articles = news_db.get_articles_by_supplier(selected_supplier)
                if articles:
                    art_df = pd.DataFrame(articles)
                    st.write(f"Articles associated with **{selected_supplier}**")
                    # show minimal details
                    st.dataframe(
                        art_df[["id", "filename", "content_length"]],
                        use_container_width=True,
                    )
                else:
                    st.info("No news articles associated with this supplier.")
    else:
        st.info("No suppliers saved in database yet.")
