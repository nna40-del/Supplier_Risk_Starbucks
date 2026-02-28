import json
import re
from typing import Any, Dict, List
from pathlib import Path

import io
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Import the news risk scoring module
from supplier_news_risk import score_article

# optional PDF support
try:
    import PyPDF2
except Exception:  # pragma: no cover - optional dependency
    PyPDF2 = None


st.set_page_config(
    page_title="Supply Risk Scoring Intake",
    page_icon="📦",
    layout="wide",
)

DB_FILE = Path(__file__).with_name("data.json")

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
                uploaded_suppliers = parsed_json.get("suppliers") if isinstance(parsed_json, dict) else None
                if not isinstance(uploaded_suppliers, list):
                    st.error("❌ Uploaded JSON must include a top-level 'suppliers' list.")
                    st.stop()

                def _normalize_name(name: Any) -> str:
                    return str(name or "").strip().lower()

                # Read current supplier database to identify truly new suppliers
                db_payload: Dict[str, Any] = {"suppliers": []}
                existing_suppliers: List[Dict[str, Any]] = []
                if DB_FILE.exists():
                    try:
                        with DB_FILE.open("r", encoding="utf-8") as f:
                            db_payload = json.load(f)
                        existing_suppliers = db_payload.get("suppliers", []) if isinstance(db_payload, dict) else []
                        if not isinstance(existing_suppliers, list):
                            existing_suppliers = []
                    except Exception:
                        existing_suppliers = []

                existing_names = {_normalize_name(s.get("name")) for s in existing_suppliers if isinstance(s, dict)}
                new_supplier_inputs: List[Dict[str, Any]] = []
                for supplier in uploaded_suppliers:
                    if not isinstance(supplier, dict):
                        continue
                    name_key = _normalize_name(supplier.get("name"))
                    if not name_key:
                        continue
                    if name_key not in existing_names:
                        new_supplier_inputs.append(supplier)
                        existing_names.add(name_key)

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
                new_supplier_name_keys = {_normalize_name(s.get("name")) for s in new_supplier_inputs}

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

                # Dedicated assessment for suppliers that are not yet in database
                if new_supplier_name_keys:
                    st.markdown("### 🆕 Candidate Supplier Risk Assessment (Not Yet in Database)")
                    new_rows = [
                        row for row in rows
                        if _normalize_name(row.get("name")) in new_supplier_name_keys
                    ]
                    if new_rows:
                        new_df = pd.DataFrame(new_rows)
                        st.dataframe(new_df, use_container_width=True, hide_index=True)
                        severe_count = int((new_df["risk_level"] == "SEVERE").sum())
                        high_count = int((new_df["risk_level"] == "HIGH").sum())
                        if severe_count > 0:
                            st.error(f"⚠️ {severe_count} new supplier(s) assessed as SEVERE risk.")
                        elif high_count > 0:
                            st.warning(f"⚠️ {high_count} new supplier(s) assessed as HIGH risk.")
                        else:
                            st.success("✅ New supplier candidates assessed as LOW/MODERATE risk.")

                    # Persist only newly discovered suppliers into the local database
                    try:
                        fresh_existing = db_payload.get("suppliers", []) if isinstance(db_payload, dict) else []
                        if not isinstance(fresh_existing, list):
                            fresh_existing = []
                        fresh_existing_names = {
                            _normalize_name(s.get("name"))
                            for s in fresh_existing
                            if isinstance(s, dict)
                        }
                        append_list: List[Dict[str, Any]] = []
                        for supplier in new_supplier_inputs:
                            supplier_name_key = _normalize_name(supplier.get("name"))
                            if supplier_name_key and supplier_name_key not in fresh_existing_names:
                                append_list.append(supplier)
                                fresh_existing_names.add(supplier_name_key)

                        if append_list:
                            fresh_existing.extend(append_list)
                            db_payload["suppliers"] = fresh_existing
                            with DB_FILE.open("w", encoding="utf-8") as f:
                                json.dump(db_payload, f, indent=4, ensure_ascii=False)
                            st.success(f"💾 Added {len(append_list)} new supplier profile(s) to database.")
                        else:
                            st.info("ℹ️ No additional supplier profiles were added to database.")
                    except Exception as persist_err:
                        st.warning(f"⚠️ Risk assessment completed, but failed to update database: {persist_err}")
                else:
                    st.info("ℹ️ All uploaded suppliers already exist in database; no new profiles added.")

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
        uploaded_news_file = st.file_uploader("Upload a JSON or TXT file with news articles", type=["json", "txt"], key="news_json")
        if uploaded_news_file is not None:
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
                                articles_list.append({"id": i, "text": p})
                            processed = True
                        except Exception:
                            st.error("Failed to parse PDF content.")
                            processed = True

                # try JSON first (unless PDF already processed)
                if not processed:
                    try:
                        news_data = json.loads(content_bytes.decode("utf-8"))
                        # normalize to list of article texts
                        if isinstance(news_data, dict):
                            if "articles" in news_data and isinstance(news_data["articles"], list):
                                for i, a in enumerate(news_data["articles"]):
                                    if isinstance(a, dict):
                                        text = a.get("text", a.get("content", json.dumps(a)))
                                    else:
                                        text = str(a)
                                    if text and str(text).strip():
                                        articles_list.append({"id": i, "text": str(text).strip()})
                            elif "text" in news_data:
                                text = news_data["text"]
                                articles_list.append({"id": 0, "text": str(text).strip()})
                            elif "content" in news_data:
                                text = news_data["content"]
                                articles_list.append({"id": 0, "text": str(text).strip()})
                            else:
                                # fallback: stringify and treat as single article
                                articles_list.append({"id": 0, "text": json.dumps(news_data)})
                        elif isinstance(news_data, list):
                            for i, item in enumerate(news_data):
                                if isinstance(item, dict):
                                    text = item.get("text", item.get("content", json.dumps(item)))
                                else:
                                    text = str(item)
                                if text and str(text).strip():
                                    articles_list.append({"id": i, "text": str(text).strip()})
                        else:
                            articles_list.append({"id": 0, "text": str(news_data)})
                    except Exception:
                        # treat as plain text file; split into paragraphs by blank lines
                        try:
                            text = content_bytes.decode("utf-8")
                        except Exception:
                            text = content_bytes.decode("latin-1")
                        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
                        for i, p in enumerate(paragraphs):
                            articles_list.append({"id": i, "text": p})
            except Exception:
                st.error("❌ Invalid or unreadable file format")

    if articles_list and st.button("🔍 Analyze Article(s) for Risk", type="primary", key="analyze_news"):
        try:
            with st.spinner("🤖 AI is analyzing the article(s)..."):
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
                    })

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
                    df_batch = pd.DataFrame([{k: v for k, v in r.items() if k not in ("raw_results", "theme_scores")} for r in batch_results])
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
