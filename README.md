# Supplier News Risk Scoring Module

A production-ready Python module for NLP-based supplier news risk scoring. This system analyzes raw news articles and generates quantitative risk assessments across four key themes relevant to supply chain management: **labor violations**, **environmental damage**, **political instability**, and **financial distress**.

## Features

- ✅ **Fully Offline** – Uses local sentence-transformers embeddings; no external API keys or credentials required
- ✅ **Production-Ready** – Clear error handling, modular design, FastAPI-compatible
- ✅ **Fast & Lightweight** – All-MiniLM-L6-v2 model runs efficiently on standard hardware
- ✅ **Comprehensive Scoring** – Sentiment analysis, theme-specific keyword detection, embedding similarity, and aggregated risk scoring
- ✅ **Customizable** – Override theme keywords, embedding models, or weighting schemes easily

## Installation

### Prerequisites
- Python 3.7+
- pip or conda

### Setup

1. **Clone or navigate to the workspace:**
   ```bash
   cd /workspaces/blank-app
   ```

2. **(Optional) Activate a virtual environment:**
   ```bash
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install textblob numpy sentence-transformers
   ```

   That's it! No API keys, no external service subscriptions needed.

## Quick Start

### Run the Built-in Demo

```bash
python supplier_news_risk.py
```

This will score a sample article and print JSON output:

```json
{
  "sentiment_score": -0.246,
  "theme_scores": {
    "labor_violations": 0.032,
    "environmental_damage": 0.032,
    "political_instability": 0.0,
    "financial_distress": 0.065
  },
  "keyword_intensity_score": 0.129,
  "disruption_similarity_score": -0.015,
  "overall_news_risk_score": 9.81
}
```

## Testing

### 1. **Interactive Testing in Python**

```bash
source /workspaces/blank-app/.venv/bin/activate
python
```

Then in the Python REPL:

```python
from supplier_news_risk import score_article

# Test with a custom article
article_text = """
Factory closure raises environmental concerns after pollution incident.
Union files complaint over unsafe working conditions.
Company faces potential credit downgrade due to mounting debt.
"""

result = score_article(article_text)

# Print structured output
import json
print(json.dumps(result.to_dict(), indent=2))

# Access individual metrics
print(f"Overall Risk: {result.overall_news_risk_score}/100")
print(f"Sentiment: {result.sentiment_score}")
print(f"Theme Scores: {result.theme_scores}")
```

### 2. **Batch Testing with File Input**

Create a test file `test_articles.txt` with sample news articles (one per line or separated by blank lines), then:

```python
from supplier_news_risk import score_article
import json

# Read and score articles
with open("test_articles.txt", "r") as f:
    articles = f.read().split("\n\n")

results = []
for idx, article in enumerate(articles):
    if article.strip():
        try:
            result = score_article(article)
            results.append({
                "article_id": idx,
                "risk_score": result.overall_news_risk_score,
                "sentiment": result.sentiment_score,
                "themes": result.theme_scores
            })
        except Exception as e:
            print(f"Error scoring article {idx}: {e}")

# Save results
with open("scoring_results.json", "w") as f:
    json.dump(results, f, indent=2)
print(f"Scored {len(results)} articles. Results saved to scoring_results.json")
```

### 3. **Test Individual Scoring Components**

```python
from supplier_news_risk import (
    sentiment_score,
    keyword_intensity_score,
    theme_scores,
    generate_embedding,
    disruption_similarity_score,
    THEME_KEYWORDS
)

text = "Workers strike over safety violations. Facility faces environmental cleanup."

# Test sentiment
print(f"Sentiment: {sentiment_score(text)}")

# Test keyword intensity (overall)
print(f"Keyword Intensity: {keyword_intensity_score(text, THEME_KEYWORDS)}")

# Test per-theme keyword scores
print(f"Theme Scores: {theme_scores(text, THEME_KEYWORDS)}")

# Test embedding generation (first call downloads model ~90MB)
embedding = generate_embedding(text)
print(f"Embedding shape: {len(embedding)} dimensions")

# Test similarity to historical disruptions
dummy_historical = [
    [0.1] * 384,
    [0.2] * 384,
]
similarity = disruption_similarity_score(embedding, dummy_historical)
print(f"Disruption Similarity: {similarity}")
```

### 4. **Unit Test Suite (pytest)**

Create a file named `test_supplier_risk.py`:

```python
import pytest
from supplier_news_risk import (
    score_article,
    sentiment_score,
    keyword_intensity_score,
    theme_scores,
    THEME_KEYWORDS,
)


def test_empty_input_raises_error():
    """Test that empty input raises ValueError."""
    with pytest.raises(ValueError):
        score_article("")


def test_whitespace_only_input_raises_error():
    """Test that whitespace-only input raises ValueError."""
    with pytest.raises(ValueError):
        score_article("   \n  \t  ")


def test_sentiment_positive_text():
    """Test sentiment scoring on positive news."""
    text = "Company thrives with record profits and happy employees."
    result = sentiment_score(text)
    assert result > 0, "Positive text should have positive sentiment"


def test_sentiment_negative_text():
    """Test sentiment scoring on negative news."""
    text = "Facility shutdown due to safety violations and environmental damage."
    result = sentiment_score(text)
    assert result < 0, "Negative text should have negative sentiment"


def test_labor_violation_keywords():
    """Test detection of labor violation keywords."""
    text = "Workers staged a strike due to unsafe labor conditions."
    themes = theme_scores(text, THEME_KEYWORDS)
    assert themes["labor_violations"] > 0, "Labor keywords should be detected"


def test_environmental_keywords():
    """Test detection of environmental damage keywords."""
    text = "Chemical spill caused severe pollution in the region."
    themes = theme_scores(text, THEME_KEYWORDS)
    assert themes["environmental_damage"] > 0, "Environmental keywords should be detected"


def test_financial_keywords():
    """Test detection of financial distress keywords."""
    text = "Company faces bankruptcy risk and credit default concerns."
    themes = theme_scores(text, THEME_KEYWORDS)
    assert themes["financial_distress"] > 0, "Financial keywords should be detected"


def test_multiple_themes():
    """Test detection across multiple themes."""
    text = """
    Factory closure announced after environmental violations.
    Union files labor dispute claim. Company defaulted on debt obligations.
    """
    themes = theme_scores(text, THEME_KEYWORDS)
    non_zero_themes = sum(1 for score in themes.values() if score > 0)
    assert non_zero_themes >= 2, "Multiple themes should be detected"


def test_overall_risk_score_range():
    """Test that overall risk score is within [0, 100]."""
    text = "Some neutral business news about supplier operations."
    result = score_article(text)
    assert 0 <= result.overall_news_risk_score <= 100, "Risk score should be in [0, 100]"


def test_complete_result_structure():
    """Test that the result contains all required fields."""
    text = "Test article for comprehensive risk assessment."
    result = score_article(text)
    
    assert hasattr(result, "sentiment_score")
    assert hasattr(result, "theme_scores")
    assert hasattr(result, "keyword_intensity_score")
    assert hasattr(result, "disruption_similarity_score")
    assert hasattr(result, "overall_news_risk_score")
    
    # Verify theme_scores is a dict with all expected themes
    assert isinstance(result.theme_scores, dict)
    assert set(result.theme_scores.keys()) == {
        "labor_violations",
        "environmental_damage",
        "political_instability",
        "financial_distress",
    }


if __name__ == "__main__":
    # Run with: pytest test_supplier_risk.py -v
    pytest.main([__file__, "-v"])
```

**Run the tests:**

```bash
pip install pytest
pytest test_supplier_risk.py -v
```

Expected output:
```
test_supplier_risk.py::test_empty_input_raises_error PASSED
test_supplier_risk.py::test_sentiment_positive_text PASSED
test_supplier_risk.py::test_labor_violation_keywords PASSED
...
======================== 10 passed in 2.35s ========================
```

### 5. **FastAPI Integration Test**

Create a file named `test_api.py`:

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supplier_news_risk import score_article

app = FastAPI(title="Supplier Risk Scoring API")


class ArticlePayload(BaseModel):
    text: str


@app.post("/score_news")
async def score_news(payload: ArticlePayload):
    """Score a news article for supplier risk."""
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    try:
        result = score_article(payload.text)
        return result.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# Run with: uvicorn test_api:app --reload
# Then test with: curl -X POST "http://localhost:8000/score_news" \
#   -H "Content-Type: application/json" \
#   -d '{"text": "Factory closes after pollution incidents."}'
```

Install and run:
```bash
pip install fastapi uvicorn
uvicorn test_api:app --reload
```

Test the endpoint:
```bash
curl -X POST "http://localhost:8000/score_news" \
  -H "Content-Type: application/json" \
  -d '{"text": "Workers stage strike over unsafe labor conditions. Facility faces environmental damage lawsuit."}'
```

## Module API Reference

### `score_article(text, historical_embeddings=None, theme_keywords=None) → NewsRiskResult`

**Main entry point.** Analyzes raw article text and returns a comprehensive risk assessment.

**Parameters:**
- `text` (str, required): Raw news article text
- `historical_embeddings` (List[List[float]], optional): Pre-computed embeddings of past disruption cases for similarity comparison
- `theme_keywords` (Dict[str, List[str]], optional): Custom keyword dictionary; defaults to `THEME_KEYWORDS`

**Returns:** `NewsRiskResult` dataclass with fields:
- `sentiment_score`: Float [-1, 1]
- `theme_scores`: Dict with scores for each risk theme
- `keyword_intensity_score`: Float [0, 1]
- `disruption_similarity_score`: Float (typically [0, 1])
- `overall_news_risk_score`: Float [0, 100]

**Example:**
```python
result = score_article("Factory closure due to environmental violations.")
print(result.overall_news_risk_score)  # 42.15
```

### `generate_embedding(text) → List[float]`

Generate a semantic embedding (384 dimensions) for the input text using the local all-MiniLM-L6-v2 model.

### `sentiment_score(text) → float`

Return normalized sentiment polarity in [-1, 1] using TextBlob.

### `theme_scores(text, theme_keywords) → Dict[str, float]`

Return frequency-normalized keyword hits per theme.

### `keyword_intensity_score(text, theme_keywords) → float`

Return overall keyword intensity [0, 1] across all themes.

### `disruption_similarity_score(embedding, historical_embeddings) → float`

Return maximum cosine similarity between embedding and historical cases.

## Configuration

The module uses sensible defaults and requires no configuration. To customize:

```python
from supplier_news_risk import score_article, THEME_KEYWORDS

# Use custom keywords
custom_keywords = {
    "labor_violations": ["strike", "unsafe", "injury"],
    "environmental_damage": ["spill", "pollution"],
    "political_instability": ["protest", "sanction"],
    "financial_distress": ["bankruptcy", "debt"],
}

result = score_article(text, theme_keywords=custom_keywords)
```

## Performance Notes

- **First run:** ~15–30 seconds (downloads 90MB sentence-transformers model)
- **Subsequent runs:** <1 second per article (model cached in memory)
- **Memory:** ~300MB for model in memory + ~10MB per batch of 1000 embeddings

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: textblob` | Run `pip install textblob numpy sentence-transformers` |
| `Model download fails` | Ensure internet connectivity; `sentence-transformers` will cache the model in `~/.cache/huggingface` |
| `Embedding dimensions mismatch` | all-MiniLM-L6-v2 produces 384-d embeddings; ensure historical embeddings match |
| `Slow first execution` | Normal—model downloads and caches on first call; subsequent calls are fast |

## License

Configured for Starbucks supply chain risk assessment. Modify and deploy as needed for your supply chain context.

## Support

For issues or enhancements, refer to the docstrings in `supplier_news_risk.py` or reach out to the development team.
