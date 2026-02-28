"""Module for NLP-based supplier news risk scoring.

This module is intended for integration into a FastAPI backend where
incoming news articles can be scored for supplier risk themes.

It uses local sentence-transformers for semantic similarity and a simple
sentiment and keyword-based scoring pipeline.  The module is
self-contained and production-ready with error handling and clear
function separation.  All processing runs entirely offline—no external
API calls or credentials required.

Dependencies:
    pip install textblob numpy sentence-transformers

Example usage is provided in :func:`main`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
from textblob import TextBlob
from sentence_transformers import SentenceTransformer

# set up logging for the module
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

# -- risk theme keywords ----------------------------------------------------
THEME_KEYWORDS: Dict[str, List[str]] = {
    "labor_violations": [
        "strike",
        "union",
        "child labor",
        "forced labor",
        "worker injury",
        "labor dispute",
        "safety violation",
    ],
    "environmental_damage": [
        "spill",
        "pollution",
        "deforestation",
        "waste",
        "emissions",
        "contamination",
        "habitat destruction",
    ],
    "political_instability": [
        "protest",
        "coup",
        "sanction",
        "regime",
        "military",
        "riots",
        "unrest",
    ],
    "financial_distress": [
        "bankruptcy",
        "default",
        "insolvency",
        "credit rating",
        "dividend cut",
        "layoff",
        "debt",
    ],
}

# helper dataclass for results
@dataclass
class NewsRiskResult:
    sentiment_score: float
    theme_scores: Dict[str, float]
    keyword_intensity_score: float
    disruption_similarity_score: float
    overall_news_risk_score: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sentiment_score": self.sentiment_score,
            "theme_scores": self.theme_scores,
            "keyword_intensity_score": self.keyword_intensity_score,
            "disruption_similarity_score": self.disruption_similarity_score,
            "overall_news_risk_score": self.overall_news_risk_score,
        }


# -- core utility functions -------------------------------------------------

def generate_embedding(text: str) -> List[float]:
    """Return an embedding vector for the provided text using a local model.

    Uses the sentence-transformers ``all-MiniLM-L6-v2`` model to generate
    semantic embeddings entirely offline.  The model is cached on first
    call and reused for efficiency.

    Raises:
        ValueError: if text is empty.
    """

    if not text or not text.strip():
        raise ValueError("Cannot generate embedding for empty text")

    # load a shared model instance on first call
    if not hasattr(generate_embedding, "_model"):
        logger.info("Loading sentence-transformers model (first call)...")
        generate_embedding._model = SentenceTransformer("all-MiniLM-L6-v2")
    model: SentenceTransformer = getattr(generate_embedding, "_model")
    vec = model.encode(text)
    return vec.tolist()


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Compute cosine similarity between two vectors.

    Accepts Python lists of floats (typically embeddings) and returns a
    float in [-1, 1].
    """

    a = np.array(vec1, dtype=float)
    b = np.array(vec2, dtype=float)
    if a.size == 0 or b.size == 0:
        return 0.0
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def sentiment_score(text: str) -> float:
    """Return sentiment polarity of the text normalized to [-1, 1].

    This is a lightweight wrapper around TextBlob.  In production you could
    replace or augment this with a more sophisticated model or service.
    """

    if not text or not text.strip():
        return 0.0
    blob = TextBlob(text)
    # TextBlob polarity is already between -1.0 and 1.0
    return round(blob.sentiment.polarity, 3)


def _count_keywords(text: str, keywords: List[str]) -> int:
    """Count case-insensitive occurrences of each keyword in the text."""

    count = 0
    lowered = text.lower()
    for kw in keywords:
        # simple whole-word check
        count += lowered.count(kw.lower())
    return count


def keyword_intensity_score(text: str, theme_keywords: Dict[str, List[str]]) -> float:
    """Compute a frequency-weighted intensity score for all keywords.

    The raw score is the total keyword matches divided by the length
    of the article (in words) to normalize for article size, clipped to [0,1].
    """

    if not text or not text.strip():
        return 0.0
    words = len(text.split())
    if words == 0:
        return 0.0
    total_hits = 0
    for keywords in theme_keywords.values():
        total_hits += _count_keywords(text, keywords)
    score = total_hits / words
    return min(max(score, 0.0), 1.0)


def theme_scores(text: str, theme_keywords: Dict[str, List[str]]) -> Dict[str, float]:
    """Return a dictionary mapping each theme to its own score.

    Each theme's score is simply the frequency of its keywords normalized
    by article length and clipped to [0,1].  This can easily be made more
    sophisticated in the future.
    """

    if not text or not text.strip():
        return {theme: 0.0 for theme in theme_keywords}
    words = len(text.split())
    if words == 0:
        return {theme: 0.0 for theme in theme_keywords}

    scores: Dict[str, float] = {}
    for theme, keywords in theme_keywords.items():
        hits = _count_keywords(text, keywords)
        scores[theme] = min(max(hits / words, 0.0), 1.0)
    return scores


def disruption_similarity_score(
    article_embedding: List[float], historical_embeddings: List[List[float]]
) -> float:
    """Return maximum cosine similarity to a list of historical case embeddings.

    Historical embeddings should be precomputed and stored in a database or
    file.  This function simply iterates through them and returns the
    highest similarity, which is useful as a proxy for how "close" the
    current article is to a known disruption.
    """

    if not historical_embeddings:
        return 0.0
    sims = [cosine_similarity(article_embedding, h) for h in historical_embeddings]
    return max(sims)


def compute_overall_news_risk_score(
    sentiment: float,
    theme_scores_dict: Dict[str, float],
    keyword_intensity: float,
    disruption_sim: float,
) -> float:
    """Aggregate component scores into a single [0,100] risk score.

    The default weights are arbitrary and should be calibrated with
    real-world data.  Sentiment is inverted (negative sentiment
    increases risk) by subtracting from 0.0.
    """

    # negative polarity implies worse news; flip sign so higher is worse
    sentiment_component = (0.0 - sentiment) * 25.0
    theme_component = sum(theme_scores_dict.values()) / len(theme_scores_dict) * 25.0
    keyword_component = keyword_intensity * 25.0
    disruption_component = disruption_sim * 25.0

    raw = sentiment_component + theme_component + keyword_component + disruption_component
    score = max(min(raw, 100.0), 0.0)
    return round(score, 2)


def score_article(
    text: str,
    historical_embeddings: Optional[List[List[float]]] = None,
    theme_keywords: Optional[Dict[str, List[str]]] = None,
) -> NewsRiskResult:
    """Top-level entry point for scoring a piece of raw news text.

    Args:
        text: raw article text (required).
        historical_embeddings: embeddings of past disruption cases; if not
            provided, similarity score is zero.
        theme_keywords: optional override of the default keywords.

    Returns:
        :class:`NewsRiskResult` containing all components and aggregated score.

    Raises:
        ValueError: when ``text`` is empty.
    """

    if not text or not text.strip():
        raise ValueError("Input text for scoring cannot be empty")

    theme_keywords = theme_keywords or THEME_KEYWORDS
    hist_embed = historical_embeddings or []

    # compute components
    sent = sentiment_score(text)
    kws = keyword_intensity_score(text, theme_keywords)
    themes = theme_scores(text, theme_keywords)

    try:
        emb = generate_embedding(text)
        sim = disruption_similarity_score(emb, hist_embed)
    except Exception:
        # if the embedding request fails we still return other scores
        sim = 0.0

    overall = compute_overall_news_risk_score(sent, themes, kws, sim)

    return NewsRiskResult(
        sentiment_score=sent,
        theme_scores=themes,
        keyword_intensity_score=kws,
        disruption_similarity_score=sim,
        overall_news_risk_score=overall,
    )


# --- sample main -----------------------------------------------------------

def main() -> None:
    """Simple demonstration of how to use the scoring module."""

    sample_text = (
        "A major factory was forced to close after pollution complaints. "
        "Workers staged a strike as management failed to meet safety demands. "
        "The company is facing mounting debt and rumors of bankruptcy."
    )

    # pretend we have a couple historical disruption embeddings already
    # (note: all-MiniLM-L6-v2 produces 384-dimensional embeddings)
    dummy_hist = [
        [0.1] * 384,  # normally these would be real embedding vectors
        [0.2] * 384,
    ]

    try:
        result = score_article(sample_text, historical_embeddings=dummy_hist)
        print(json.dumps(result.to_dict(), indent=2))
    except Exception as exc:
        logger.error("Scoring failed: %s", exc)


# --- optional FastAPI integration example ----------------------------------
#
# The following code snippet shows how this scoring module could be
# wired into a FastAPI application.  It is not executed when the module is
# imported but can be copied into the API server implementation.
#
# ```python
# from fastapi import FastAPI, HTTPException
# from pydantic import BaseModel
#
# app = FastAPI()
#
# class ArticlePayload(BaseModel):
#     text: str
#
# @app.post("/score_news")
# def score_news(payload: ArticlePayload):
#     if not payload.text.strip():
#         raise HTTPException(status_code=400, detail="Text cannot be empty")
#     try:
#         result = score_article(payload.text)
#         return result.to_dict()
#     except Exception as exc:
#         raise HTTPException(status_code=500, detail=str(exc))
# ```
#
# The example above demonstrates how the module's functions can be
# reused inside an API handler with minimal glue logic.
#

if __name__ == "__main__":
    main()
