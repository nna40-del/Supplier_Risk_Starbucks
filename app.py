"""
Supplier Risk Scoring & News Analysis Platform
Professional supply chain risk assessment with integrated supplier scoring and news analysis.
"""

import json
import re
from typing import Any, Dict, List
import io
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import datetime
import unicodedata

# Import custom modules
from supplier_news_risk import score_article
from database import SupplierDatabase
from news_database import NewsDatabase

# Optional PDF support
try:
    import PyPDF2
except Exception:
    PyPDF2 = None

# ============================================================================
# PAGE CONFIGURATION
# ============================================================================
st.set_page_config(
    page_title="Supply Risk Scoring Intake",
    page_icon="📦",
    layout="wide",
)

# ============================================================================
# SESSION STATE INITIALIZATION
# ============================================================================
if "last_update" not in st.session_state:
    st.session_state.last_update = None
if "data_refresh_trigger" not in st.session_state:
    st.session_state.data_refresh_trigger = 0
if "selected_supplier" not in st.session_state:
    st.session_state.selected_supplier = None
if "selected_tab" not in st.session_state:
    st.session_state.selected_tab = "📊 Dashboard"

# ============================================================================
# CONSTANTS & CONFIGURATION
# ============================================================================
RISK_COLORS = {
    "LOW": "#28a745",
    "MODERATE": "#ffc107",
    "HIGH": "#fd7e14",
    "SEVERE": "#dc3545",
}

RISK_EMOJIS = {
    "LOW": "🟢",
    "MODERATE": "🟡",
    "HIGH": "🔴",
    "SEVERE": "⚫",
}

SCORING_WEIGHTS = {
    "fs": 35,
    "rc": 25,
    "op": 25,
    "fin": 15,
}

RISK_THRESHOLDS = {
    "low": 30,
    "moderate": 50,
    "high": 80,
}

RISK_RECOMMENDATIONS = {
    "LOW": {
        "emoji": "🟢",
        "color": "#28a745",
        "description": "Low Risk",
        "recommendation": "✅ **Maintain current monitoring.** No immediate action required.",
        "actions": [
            "• Monitor supplier quarterly",
            "• Keep existing contracts in place",
            "• No escalated action needed",
        ],
    },
    "MODERATE": {
        "emoji": "🟡",
        "color": "#ffc107",
        "description": "Moderate Risk",
        "recommendation": "⚠️ **Increase monitoring and communication.**",
        "actions": [
            "• Request supplier response within 5 business days",
            "• Schedule management review call",
            "• Increase monitoring frequency to bi-weekly",
            "• Document all findings for audit trail",
        ],
    },
    "HIGH": {
        "emoji": "🔴",
        "color": "#fd7e14",
        "description": "High Risk",
        "recommendation": "🚨 **Escalate immediately.**",
        "actions": [
            "• Schedule urgent supplier meeting",
            "• Request detailed remediation plan",
            "• Consider on-site audit/inspection",
            "• Identify backup suppliers",
            "• Daily monitoring until resolved",
            "• Brief procurement team and leadership",
        ],
    },
    "SEVERE": {
        "emoji": "⚫",
        "color": "#dc3545",
        "description": "Severe Risk",
        "recommendation": "🛑 **CRITICAL - Take immediate action.**",
        "actions": [
            "• URGENT: Escalate to executive leadership",
            "• Activate business continuity plan",
            "• Initiate supplier contingency sourcing immediately",
            "• Cease non-emergency orders",
            "• Conduct legal/compliance review",
            "• Communicate with affected stakeholders",
            "• Real-time monitoring and daily reporting",
        ],
    },
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def normalize_text(text: str) -> str:
    """Normalize text for better matching."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("utf-8")
    text = re.sub(r"[_\-]", " ", text)
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.lower()


def get_risk_score_category(score: int) -> str:
    """Return risk category based on score."""
    if score <= RISK_THRESHOLDS["low"]:
        return "LOW"
    elif score <= RISK_THRESHOLDS["moderate"]:
        return "MODERATE"
    elif score <= RISK_THRESHOLDS["high"]:
        return "HIGH"
    else:
        return "SEVERE"


def parse_percentage(s: Any) -> float:
    """Parse percentage values."""
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
    """Score food safety factor."""
    score = 0.5
    combined = " ".join([str(v).lower() for v in fs.values()])
    if "none" in combined and "recall" in combined:
        score -= 0.35
    if "recall" in combined or "class" in combined:
        score += 0.25
    if any(x in combined for x in ("sqf", "brcgs", "fssc", "gfs")):
        score -= 0.2
    if any(x in combined for x in ("no critical", "no major", "no enforcement")):
        score -= 0.15
    return min(max(score, 0.0), 1.0)


def score_regulatory(rc: Dict[str, Any]) -> float:
    """Score regulatory compliance factor."""
    score = 0.5
    combined = " ".join([str(v).lower() for v in rc.values()])
    if any(x in combined for x in ("483", "open483", "observation", "warning")):
        score += 0.35
    if any(x in combined for x in ("no 483", "no 483s", "no enforcement", "clean")):
        score -= 0.2
    if any(x in combined for x in ("compliant", "verified", "signed")):
        score -= 0.15
    return min(max(score, 0.0), 1.0)


def score_operational(op: Dict[str, Any]) -> float:
    """Score operational reliability factor."""
    score = 0.5
    combined = " ".join([str(v).lower() for v in op.values()])
    otif = parse_percentage(op.get("otif", op.get("OTIF", "")))
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
        for x in ("backup", "redundancy", "identified", "multi-site", "multi")
    ):
        score -= 0.15
    return min(max(score, 0.0), 1.0)


def score_financial(fin: Dict[str, Any]) -> float:
    """Score financial stability factor."""
    score = 0.5
    combined = " ".join([str(v).lower() for v in fin.values()])
    if any(
        x in combined for x in ("low", "stable", "satisfactory", "strong", "audited")
    ):
        score -= 0.2
    if any(
        x in combined
        for x in ("moderate", "moderately", "concentration", "seasonal", "private")
    ):
        score += 0.05
    if (
        any(x in combined for x in ("credit risk", "creditreview", "credit"))
        and "moderate" in combined
    ):
        score += 0.15
    return min(max(score, 0.0), 1.0)


def compute_supplier_risks(
    payload: Dict[str, Any], weights: Dict[str, float]
) -> List[Dict[str, Any]]:
    """Compute risk scores for suppliers."""
    suppliers = payload.get("suppliers") or []
    results = []

    for s in suppliers:
        fs = s.get("foodSafetyQuality", {})
        rc = s.get("regulatoryCompliance", {})
        op = s.get("operationalReliability", {})
        fin = s.get("financialStability", {})

        total = sum(weights.get(w, 0) for w in ["fs", "rc", "op", "fin"])
        if total <= 0:
            w_fs, w_rc, w_op, w_fin = 0.35, 0.25, 0.25, 0.15
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
        risk_level = get_risk_score_category(risk_score)

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


# ============================================================================
# PAGE TITLE & TAB NAVIGATION
# ============================================================================
st.title("🚨 Supplier Risk Scoring & News Analysis")
st.caption(
    "Professional supply chain risk assessment platform with integrated supplier scoring and news analysis."
)

# Create tab navigation using radio buttons
tab_names = [
    "📊 Dashboard",
    "📦 Supplier Data",
    "📰 News Analysis",
    "🔍 Supplier Insights",
]

st.session_state.selected_tab = st.radio(
    "Navigation:",
    tab_names,
    index=tab_names.index(st.session_state.selected_tab)
    if st.session_state.selected_tab in tab_names
    else 0,
    horizontal=True,
)

st.markdown("---")

# ============================================================================
# CONDITIONAL TAB RENDERING
# ============================================================================

if st.session_state.selected_tab == "📊 Dashboard":
    st.markdown("## Dashboard Overview")
    st.markdown(
        "High-level view of your supply chain risk landscape with key metrics and alerts."
    )

    st.markdown("---")

    db = SupplierDatabase()
    news_db = NewsDatabase()

    all_suppliers = db.get_all_suppliers()
    news_stats = news_db.get_supplier_news_stats()

    # Calculate summary metrics using combined risk scores (like supplier insights)
    total_suppliers = len(all_suppliers)
    suppliers_with_news = len([s for s in all_suppliers if s.get("name") in news_stats])

    # Calculate combined risk metrics for all suppliers
    combined_risk_data = []
    for supplier in all_suppliers:
        supplier_name = supplier.get("name")
        risk_score = supplier.get("risk_score", 0)
        original_risk_level = supplier.get("risk_level", "UNKNOWN")

        # Check if supplier has news articles
        supplier_news = news_stats.get(supplier_name, {})
        count = supplier_news.get("count", 0)
        avg_news = float(supplier_news.get("avg_score", 0.0) or 0.0)

        if count > 0:
            # Use combined score
            combined_score = round((risk_score + avg_news) / 2, 1)
            combined_risk_level = get_risk_score_category(int(combined_score))
            display_score = combined_score
            display_level = combined_risk_level
        else:
            # Use original supplier score
            display_score = risk_score
            display_level = original_risk_level

        combined_risk_data.append(
            {
                "display_score": display_score,
                "display_level": display_level,
                "has_news": count > 0,
            }
        )

    high_risk_suppliers = len(
        [s for s in combined_risk_data if s.get("display_level") in ["HIGH", "SEVERE"]]
    )
    avg_risk_score = (
        (
            sum(s.get("display_score", 0) for s in combined_risk_data)
            / len(combined_risk_data)
        )
        if combined_risk_data
        else 0
    )

    # Create sub-tabs within Dashboard
    dashboard_tab1, dashboard_tab2 = st.tabs(["📈 Overview", "🚨 Alerts"])

    with dashboard_tab1:
        st.markdown("### 📈 Key Performance Indicators")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "Total Suppliers",
                total_suppliers,
                delta=f"{suppliers_with_news} have news"
                if suppliers_with_news > 0
                else None,
            )
        with col2:
            st.metric("Avg Risk Score", f"{avg_risk_score:.1f}/100")
        with col3:
            st.metric("⚠️ High/Severe Risk", high_risk_suppliers)
        with col4:
            st.metric("📰 Suppliers w/ News", suppliers_with_news)

    with dashboard_tab2:
        # Display alerts for critical suppliers based on combined risk scores
        if all_suppliers:
            news_db = NewsDatabase()
            news_stats = news_db.get_supplier_news_stats()

            # Calculate combined risk levels for all suppliers
            suppliers_with_combined_risk = []
            for supplier in all_suppliers:
                supplier_name = supplier.get("name")
                risk_score = supplier.get("risk_score", 0)
                original_risk_level = supplier.get("risk_level", "UNKNOWN")

                # Check if supplier has news articles
                supplier_news = news_stats.get(supplier_name, {})
                count = supplier_news.get("count", 0)
                avg_news = float(supplier_news.get("avg_score", 0.0) or 0.0)

                if count > 0:
                    # Use combined score
                    combined_score = round((risk_score + avg_news) / 2, 1)
                    combined_risk_level = get_risk_score_category(int(combined_score))
                    display_score = combined_score
                    display_level = combined_risk_level
                else:
                    # Use original supplier score
                    display_score = risk_score
                    display_level = original_risk_level

                suppliers_with_combined_risk.append(
                    {
                        **supplier,
                        "display_score": display_score,
                        "display_level": display_level,
                        "has_news": count > 0,
                    }
                )

            severe_suppliers = [
                s
                for s in suppliers_with_combined_risk
                if s.get("display_level") == "SEVERE"
            ]
            high_suppliers = [
                s
                for s in suppliers_with_combined_risk
                if s.get("display_level") == "HIGH"
            ]

            if severe_suppliers:
                st.markdown("### ⚫ Critical Alerts - SEVERE Risk Suppliers")
                for supplier in severe_suppliers:
                    with st.container(border=True):
                        col1, col2 = st.columns([4, 1])
                        with col1:
                            news_indicator = (
                                " (with news analysis)"
                                if supplier.get("has_news")
                                else ""
                            )
                            st.error(
                                f"🛑 **{supplier.get('name')}** - Combined Risk Score: {supplier.get('display_score')}/100{news_indicator}\n\n"
                                f"Immediate action required. Escalate to leadership."
                            )
                        with col2:
                            st.metric("Risk Level", "SEVERE")

            if high_suppliers and not severe_suppliers:
                st.markdown("### 🔴 Warnings - HIGH Risk Suppliers")
                for supplier in high_suppliers:
                    with st.container(border=True):
                        col1, col2 = st.columns([4, 1])
                        with col1:
                            news_indicator = (
                                " (with news analysis)"
                                if supplier.get("has_news")
                                else ""
                            )
                            st.warning(
                                f"⚠️ **{supplier.get('name')}** - Combined Risk Score: {supplier.get('display_score')}/100{news_indicator}\n\n"
                                f"Enhanced monitoring and contingency planning recommended."
                            )
                        with col2:
                            st.metric("Risk Level", "HIGH")
        else:
            st.info(
                "📊 No supplier data uploaded yet. Start by uploading supplier data in the 'Supplier Data' tab."
            )
# TAB 2: SUPPLIER DATA MANAGEMENT
# ============================================================================
if st.session_state.selected_tab == "📦 Supplier Data":
    st.markdown("## Supplier Data Management")
    st.markdown(
        "Upload and manage supplier JSON data. The system scores them based on key risk factors."
    )

    st.markdown("### 📤 Upload Supplier JSON Data")

    uploaded_file = st.file_uploader(
        "Select a JSON file with supplier data", type=["json"], key="supplier_json"
    )

    if uploaded_file is not None:
        st.info(f"📄 Selected file: **{uploaded_file.name}**")

        if st.button(
            "✅ Submit & Score Suppliers", type="primary", key="submit_supplier"
        ):
            try:
                with st.spinner("🤖 Processing supplier data..."):
                    parsed_json = json.load(uploaded_file)
                    weights = {
                        "fs": SCORING_WEIGHTS["fs"],
                        "rc": SCORING_WEIGHTS["rc"],
                        "op": SCORING_WEIGHTS["op"],
                        "fin": SCORING_WEIGHTS["fin"],
                    }
                    scored = compute_supplier_risks(parsed_json, weights)

                    # Save to database
                    db = SupplierDatabase()
                    suppliers_list = parsed_json.get("suppliers", [])

                    saved_count = 0
                    for i, supplier in enumerate(suppliers_list):
                        try:
                            supplier_id = db.save_supplier(supplier)
                            scored_result = scored[i] if i < len(scored) else None
                            if scored_result and supplier_id:
                                db.save_scoring_result(
                                    supplier_id=supplier_id,
                                    risk_score=scored_result.get("risk_score", 0),
                                    risk_level=scored_result.get(
                                        "risk_level", "UNKNOWN"
                                    ),
                                    subscores=scored_result.get("_subscores", {}),
                                )
                                saved_count += 1
                        except Exception as e:
                            st.error(f"Error saving {supplier.get('name')}: {str(e)}")

                    st.success(
                        f"✅ **{saved_count} supplier(s) scored and saved successfully!**"
                    )
                    st.session_state.last_update = datetime.datetime.now()
                    st.session_state.data_refresh_trigger += 1

                    # Build and display results
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

                    st.markdown("### 📋 Scored Suppliers Summary")
                    col1, col2, col3, col4 = st.columns(4)
                    counts = df["risk_level"].value_counts().to_dict()
                    col1.metric("🟢 Low", counts.get("LOW", 0))
                    col2.metric("🟡 Moderate", counts.get("MODERATE", 0))
                    col3.metric("🔴 High", counts.get("HIGH", 0))
                    col4.metric("⚫ Severe", counts.get("SEVERE", 0))

                    avg_score = df["risk_score"].mean() if not df.empty else 0
                    st.info(f"**Average risk score:** {avg_score:.1f} / 100")

                    st.dataframe(df, use_container_width=True, hide_index=True)

                    csv = df.to_csv(index=False)
                    st.download_button(
                        "📥 Download Scored Results (CSV)",
                        csv,
                        file_name="scored_suppliers.csv",
                        mime="text/csv",
                    )

            except json.JSONDecodeError:
                st.error("❌ Invalid JSON file. Please upload a valid .json document.")
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")

    st.markdown("---")
    st.markdown("### 📊 Existing Suppliers in Database")

    db = SupplierDatabase()
    all_suppliers = db.get_all_suppliers()

    if all_suppliers:
        supplier_df = pd.DataFrame(
            [
                {
                    "Name": s.get("name"),
                    "Risk Score": s.get("risk_score", "N/A"),
                    "Risk Level": s.get("risk_level", "UNKNOWN"),
                    "Food Safety": s.get("foodSafety", "N/A"),
                    "Regulatory": s.get("regulatory", "N/A"),
                    "Operational": s.get("operational", "N/A"),
                    "Financial": s.get("financial", "N/A"),
                }
                for s in all_suppliers
            ]
        )
        st.dataframe(supplier_df, use_container_width=True, hide_index=True)
    else:
        st.info(
            "🚀 No supplier data uploaded yet. Upload a JSON file above to get started."
        )

# ============================================================================
# TAB 3: NEWS ANALYSIS
# ============================================================================
if st.session_state.selected_tab == "📰 News Analysis":
    st.markdown("## News Article Analysis")
    st.markdown("Upload and analyze news articles for risk indicators.")

    st.markdown("### 📤 Upload News Articles")

    input_method = st.radio(
        "Choose input method:",
        ["📄 Paste News Article", "📁 Upload File (JSON or TXT)"],
    )

    articles_list: List[Dict[str, Any]] = []

    if input_method == "📄 Paste News Article":
        st.markdown("#### Paste your news article below:")
        txt = st.text_area(
            "News Article Content:",
            height=200,
            placeholder="Paste the full text of a news article about a supplier...",
            key="news_text",
        )
        if txt and txt.strip():
            articles_list = [{"id": 0, "text": txt.strip()}]
    else:
        uploaded_news_files = st.file_uploader(
            "Upload file(s) with news articles (JSON or TXT)",
            type=["json", "txt"],
            accept_multiple_files=True,
            key="news_json",
        )
        if uploaded_news_files:
            for uploaded_news_file in uploaded_news_files:
                try:
                    content_bytes = uploaded_news_file.read()
                    try:
                        news_data = json.loads(content_bytes.decode("utf-8"))
                        if isinstance(news_data, dict) and "articles" in news_data:
                            for a in news_data["articles"]:
                                text = a.get("text") if isinstance(a, dict) else str(a)
                                if text and str(text).strip():
                                    articles_list.append(
                                        {
                                            "id": len(articles_list),
                                            "text": str(text).strip(),
                                            "filename": uploaded_news_file.name,
                                        }
                                    )
                        elif isinstance(news_data, list):
                            for item in news_data:
                                text = (
                                    item.get("text")
                                    if isinstance(item, dict)
                                    else str(item)
                                )
                                if text and str(text).strip():
                                    articles_list.append(
                                        {
                                            "id": len(articles_list),
                                            "text": str(text).strip(),
                                            "filename": uploaded_news_file.name,
                                        }
                                    )
                    except json.JSONDecodeError:
                        text = content_bytes.decode("utf-8")
                        paragraphs = [
                            p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()
                        ]
                        for p in paragraphs:
                            articles_list.append(
                                {
                                    "id": len(articles_list),
                                    "text": p,
                                    "filename": uploaded_news_file.name,
                                }
                            )
                except Exception as e:
                    st.error(f"Error processing {uploaded_news_file.name}: {str(e)}")

    st.info("""
    **📋 News Risk Scoring:**
    - **Scale:** 0-100 (0=Low risk, 100=High risk)
    - **Factors:** Sentiment, keywords (strikes, bankruptcy, etc.), disruption themes
    - **Low (0-30):** Positive news, expansions
    - **Moderate (30-50):** Mixed news with some risk
    - **High (50-80):** Concerning issues
    - **Severe (80-100):** Critical disruptions
    """)

    if articles_list and st.button(
        "🔍 Analyze Article(s) for Risk", type="primary", key="analyze_news"
    ):
        try:
            with st.spinner("🤖 Analyzing articles..."):
                news_db = NewsDatabase()
                sup_db = SupplierDatabase()
                supplier_names = [
                    s.get("name") for s in sup_db.get_all_suppliers() if s.get("name")
                ]

                batch_results: List[Dict[str, Any]] = []
                for entry in articles_list:
                    text = entry.get("text", "")
                    if not text or not str(text).strip():
                        continue

                    res = score_article(text)
                    score_val = res.overall_news_risk_score
                    level = get_risk_score_category(int(score_val))
                    rec = RISK_RECOMMENDATIONS.get(level, RISK_RECOMMENDATIONS["LOW"])

                    batch_results.append(
                        {
                            "id": entry.get("id"),
                            "excerpt": (text[:120] + "...")
                            if len(text) > 120
                            else text,
                            "overall_risk_score": score_val,
                            "risk_level": level,
                            "recommendation": rec["recommendation"],
                            "sentiment_score": res.sentiment_score,
                            "keyword_intensity_score": res.keyword_intensity_score,
                            "disruption_similarity_score": res.disruption_similarity_score,
                            "theme_scores": res.theme_scores,
                            "raw_results": res.to_dict(),
                            "article_text": text,
                            "filename": entry.get("filename", "pasted_text.txt"),
                        }
                    )

                # Save to database
                saved_count = 0
                for i, result in enumerate(batch_results):
                    try:
                        filename = result.get("filename", f"news_article_{i + 1}.txt")
                        supplier_match = None

                        article_text_normalized = normalize_text(result["article_text"])
                        for name in supplier_names:
                            if name:
                                name_normalized = normalize_text(name)
                                if name_normalized in article_text_normalized:
                                    supplier_match = name
                                    break

                        article_id = news_db.save_article(
                            filename,
                            result["article_text"],
                            supplier_name=supplier_match,
                        )
                        if article_id:
                            news_db.save_scoring_result(
                                article_id=article_id,
                                overall_risk_score=result["overall_risk_score"],
                                risk_level=result["risk_level"],
                                sentiment_score=result["sentiment_score"],
                                keyword_intensity_score=result[
                                    "keyword_intensity_score"
                                ],
                                disruption_similarity_score=result[
                                    "disruption_similarity_score"
                                ],
                                theme_scores=result["theme_scores"],
                                full_results=result["raw_results"],
                            )
                            saved_count += 1
                    except Exception as e:
                        st.error(f"Error saving article: {str(e)}")

                if saved_count > 0:
                    st.success(f"✅ **{saved_count} article(s) analyzed and saved.**")
                    st.session_state.last_update = datetime.datetime.now()
                    st.session_state.data_refresh_trigger += 1

                # Display results
                if len(batch_results) == 1:
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

                    st.markdown("### 🔍 Detailed Analysis")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Sentiment", f"{res['sentiment_score']:.3f}")
                    with col2:
                        st.metric(
                            "Keyword Intensity", f"{res['keyword_intensity_score']:.3f}"
                        )
                    with col3:
                        st.metric(
                            "Disruption Similarity",
                            f"{res['disruption_similarity_score']:.3f}",
                        )

                    theme_df = (
                        pd.DataFrame(
                            [
                                {"Theme": k.replace("_", " ").title(), "Score": v}
                                for k, v in res["theme_scores"].items()
                            ]
                        )
                        .sort_values("Score", ascending=False)
                        .reset_index(drop=True)
                    )

                    st.plotly_chart(
                        go.Figure(go.Bar(x=theme_df["Theme"], y=theme_df["Score"])),
                        use_container_width=True,
                    )
                    st.dataframe(
                        theme_df.style.bar(subset=["Score"], color="#fd7e14"),
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.download_button(
                        "📥 Download Results (JSON)",
                        json.dumps(single, indent=2),
                        file_name="risk_assessment.json",
                        mime="application/json",
                    )
                elif len(batch_results) > 1:
                    st.markdown("---")
                    st.markdown(
                        f"### 📊 Batch Results — {len(batch_results)} articles analyzed"
                    )

                    df_batch = pd.DataFrame(
                        [
                            {
                                k: v
                                for k, v in r.items()
                                if k
                                not in ("raw_results", "theme_scores", "article_text")
                            }
                            for r in batch_results
                        ]
                    )
                    st.dataframe(df_batch, use_container_width=True)

                    st.download_button(
                        "📥 Download Results (CSV)",
                        df_batch.to_csv(index=False),
                        file_name="risk_assessment_batch.csv",
                        mime="text/csv",
                    )

        except Exception as e:
            st.error(f"❌ Error: {str(e)}")

    # ============================================================================
    # MANAGE SAVED ARTICLES
    # ============================================================================
    st.markdown("---")
    st.markdown("### 🗂️ Manage Saved Articles")

    news_db = NewsDatabase()
    all_articles = news_db.get_all_articles()

    if all_articles:
        # Get unique suppliers from articles
        suppliers_with_articles = list(
            set(
                article.get("supplier_name")
                for article in all_articles
                if article.get("supplier_name")
            )
        )
        suppliers_with_articles.sort()

        # Add "All Suppliers" option
        supplier_options = ["All Suppliers"] + suppliers_with_articles

        selected_supplier_filter = st.selectbox(
            "Filter articles by supplier:",
            supplier_options,
            key="article_supplier_filter",
        )

        # Filter articles based on selection
        if selected_supplier_filter == "All Suppliers":
            filtered_articles = all_articles
        else:
            filtered_articles = [
                article
                for article in all_articles
                if article.get("supplier_name") == selected_supplier_filter
            ]

        st.markdown(f"**Showing {len(filtered_articles)} article(s)**")

        if filtered_articles:
            # Display articles in a table with delete buttons
            for article in filtered_articles:
                article_id = article["id"]
                filename = article["filename"]
                supplier_name = article.get("supplier_name", "N/A")
                uploaded_at = article["uploaded_at"]
                content_length = article["content_length"]

                # Get latest scoring result
                scoring_results = news_db.get_scoring_results_for_article(article_id)
                risk_level = "Not Scored"
                risk_score = "N/A"
                if scoring_results:
                    latest = scoring_results[0]
                    risk_level = latest.get("risk_level", "Not Scored")
                    risk_score = f"{latest.get('overall_risk_score', 0):.1f}"

                with st.expander(
                    f"📄 {filename} - {supplier_name} ({risk_level})", expanded=False
                ):
                    col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
                    with col1:
                        st.write(f"**Supplier:** {supplier_name}")
                    with col2:
                        st.write(f"**Risk Score:** {risk_score}")
                    with col3:
                        st.write(f"**Risk Level:** {risk_level}")
                    with col4:
                        st.write(f"**Length:** {content_length} chars")
                    with col5:
                        if st.button(
                            f"🗑️ Delete", key=f"delete_{article_id}", type="secondary"
                        ):
                            if news_db.delete_article(article_id):
                                st.success(
                                    f"✅ Article '{filename}' deleted successfully!"
                                )
                                st.session_state.data_refresh_trigger += 1
                                st.rerun()
                            else:
                                st.error(f"❌ Failed to delete article '{filename}'")

                    st.write(f"**Uploaded:** {uploaded_at}")
                    st.text_area(
                        "Article Excerpt:",
                        value=article["content"][:300] + "..."
                        if len(article["content"]) > 300
                        else article["content"],
                        height=100,
                        disabled=True,
                        key=f"excerpt_{article_id}",
                    )
        else:
            st.info(f"No articles found for supplier '{selected_supplier_filter}'.")
    else:
        st.info(
            "No saved articles yet. Upload and analyze articles above to see them here."
        )

# ============================================================================
# TAB 4: SUPPLIER INSIGHTS & COMBINED ANALYSIS
# ============================================================================
if st.session_state.selected_tab == "🔍 Supplier Insights":
    st.markdown("## Supplier Insights & Combined Analysis")
    st.markdown(
        "Detailed view of individual supplier risk profiles with integrated news analysis and tailored recommendations."
    )

    # ============================================================================
    # RISK LEVEL GUIDELINES (MOVED FROM SEPARATE TAB)
    # ============================================================================
    st.markdown("---")
    st.markdown("## 📚 Risk Level Guidelines")
    st.markdown(
        "Comprehensive guide to understanding and responding to supplier risk levels."
    )

    for level in ["LOW", "MODERATE", "HIGH", "SEVERE"]:
        rec = RISK_RECOMMENDATIONS[level]
        with st.expander(f"{rec['emoji']} **{rec['description']}**", expanded=False):
            st.markdown(f"### {rec['emoji']} {rec['description']}")
            st.write(f"**Recommendation:** {rec['recommendation']}")
            st.write("\n**Action Items:**")
            for action in rec["actions"]:
                st.write(action)

    st.markdown("---")
    st.markdown("## 🔍 Individual Supplier Analysis")

    db = SupplierDatabase()
    news_db = NewsDatabase()
    all_suppliers = db.get_all_suppliers()
    news_stats = news_db.get_supplier_news_stats()

    if all_suppliers:
        supplier_names = [s.get("name") for s in all_suppliers if s.get("name")]

        if supplier_names:
            selected_supplier_name = st.selectbox(
                "Select a supplier to view details:",
                supplier_names,
                key="insights_supplier_select",
            )

            if selected_supplier_name:
                selected_supplier = next(
                    (
                        s
                        for s in all_suppliers
                        if s.get("name") == selected_supplier_name
                    ),
                    None,
                )

                if selected_supplier:
                    risk_level = selected_supplier.get("risk_level", "UNKNOWN")
                    risk_score = selected_supplier.get("risk_score", 0)
                    risk_probability = selected_supplier.get("risk_probability", 0.0)
                    fs_score = selected_supplier.get("foodSafety", 0.0)
                    reg_score = selected_supplier.get("regulatory", 0.0)
                    op_score = selected_supplier.get("operational", 0.0)
                    fin_score = selected_supplier.get("financial", 0.0)

                    # Calculate combined score if news articles exist
                    supplier_news = news_stats.get(selected_supplier_name, {})
                    count = supplier_news.get("count", 0)
                    avg_news = float(supplier_news.get("avg_score", 0.0) or 0.0)

                    if count > 0:
                        combined_score = round((risk_score + avg_news) / 2, 1)
                        display_risk_score = combined_score
                        display_risk_level = get_risk_score_category(
                            int(combined_score)
                        )
                    else:
                        display_risk_score = risk_score
                        display_risk_level = risk_level

                    st.markdown(f"## {selected_supplier_name}")

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Risk Score", f"{display_risk_score}/100")
                    with col2:
                        st.metric("Risk Level", display_risk_level)
                    with col3:
                        st.metric("Risk Probability", f"{risk_probability * 100:.1f}%")

                    st.markdown("---")
                    st.markdown("### 🎯 Risk Analysis & News Integration")

                    # Risk Component Breakdown
                    st.markdown("#### Supplier Risk Components")
                    comp_col1, comp_col2, comp_col3, comp_col4 = st.columns(4)

                    def get_color_emoji(score):
                        if score <= 30:
                            return "🟢"
                        elif score <= 50:
                            return "🟡"
                        elif score <= 80:
                            return "🔴"
                        else:
                            return "⚫"

                    with comp_col1:
                        st.metric(
                            f"{get_color_emoji(fs_score * 100)} Food Safety",
                            f"{fs_score * 100:.1f}%",
                        )
                    with comp_col2:
                        st.metric(
                            f"{get_color_emoji(reg_score * 100)} Regulatory",
                            f"{reg_score * 100:.1f}%",
                        )
                    with comp_col3:
                        st.metric(
                            f"{get_color_emoji(op_score * 100)} Operational",
                            f"{op_score * 100:.1f}%",
                        )
                    with comp_col4:
                        st.metric(
                            f"{get_color_emoji(fin_score * 100)} Financial",
                            f"{fin_score * 100:.1f}%",
                        )

                    # Combined News Analysis
                    st.markdown("#### News Analysis Integration")
                    supplier_news = news_stats.get(selected_supplier_name, {})
                    count = supplier_news.get("count", 0)
                    avg_news = float(supplier_news.get("avg_score", 0.0) or 0.0)
                    max_news = float(supplier_news.get("max_score", 0.0) or 0.0)

                    if count > 0:
                        combined_score = round((risk_score + avg_news) / 2, 1)
                        combined_level = get_risk_score_category(int(combined_score))

                        news_col1, news_col2, news_col3, news_col4 = st.columns(4)
                        with news_col1:
                            st.metric("📰 Articles Linked", count)
                        with news_col2:
                            st.metric("📊 Avg News Risk", f"{avg_news:.1f}%")
                        with news_col3:
                            st.metric("📈 Max News Risk", f"{max_news:.1f}%")
                        with news_col4:
                            st.metric("🔗 Combined Score", f"{combined_score:.1f}%")

                        combined_rec = RISK_RECOMMENDATIONS.get(
                            combined_level, RISK_RECOMMENDATIONS["LOW"]
                        )
                        st.info(
                            f"**Combined Risk Level:** {combined_rec['emoji']} {combined_level}\n\n"
                            f"When supplier risk is merged with news analysis, the combined score becomes **{combined_score:.1f}%**."
                        )

                        # Chart comparison
                        fig = go.Figure()
                        fig.add_trace(
                            go.Bar(
                                name="Supplier Risk",
                                x=["Risk Score"],
                                y=[risk_score],
                                marker_color="#fd7e14",
                            )
                        )
                        fig.add_trace(
                            go.Bar(
                                name="Avg News Risk",
                                x=["Risk Score"],
                                y=[avg_news],
                                marker_color="#ffc107",
                            )
                        )
                        fig.add_trace(
                            go.Bar(
                                name="Combined Score",
                                x=["Risk Score"],
                                y=[combined_score],
                                marker_color="#dc3545",
                            )
                        )
                        fig.update_layout(
                            title="Supplier vs News vs Combined Risk",
                            barmode="group",
                            height=350,
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info(
                            "📰 No news articles linked to this supplier yet. Upload news data in the 'News Analysis' tab."
                        )

                    st.markdown("---")
                    st.markdown("### 📋 Tailored Recommendations")

                    rec = RISK_RECOMMENDATIONS.get(
                        display_risk_level, RISK_RECOMMENDATIONS["LOW"]
                    )

                    with st.container(border=True):
                        st.markdown(f"### {rec['emoji']} {rec['description']}")
                        st.write(rec["recommendation"])
                        st.write("\n**Action Items:**")
                        for action in rec["actions"]:
                            st.write(action)

    else:
        st.info(
            "📊 No supplier data available. Upload supplier data in the 'Supplier Data' tab first."
        )
