# How the Supplier News Risk Scoring AI Works (Simple Explanation)

Think of this AI system as a **news analyst for Starbucks' suppliers**. It reads news articles about your suppliers and tells you if there are red flags that could disrupt your coffee supply chain.

## The Big Picture

Imagine you have a coffee supplier in Brazil. One day, a news article comes out saying:

> "Factory closes after environmental violations. Workers staged a strike over unsafe conditions. Company faces bankruptcy risk."

The AI reads this article and asks itself: **"How risky is this supplier right now?"** Then it gives you a score from 0 to 100.
- **0–30** = Low risk (probably fine)
- **31–50** = Moderate risk (pay attention)
- **51–80** = High risk (serious problems)
- **81–100** = Severe risk (major trouble)

---

## How It Works (Like a Detective)

The AI acts like a trained detective investigating a supplier. It looks for clues:

### 1. **What's the Mood of the Article?** (Sentiment)
The AI reads the tone of the article—is it positive or negative?
- Positive tone = Good news → Lower risk
- Negative tone = Bad news → Higher risk

It's like if I told you, "The factory is thriving!" vs. "The factory is collapsing!"

### 2. **What Problems Are Mentioned?** (Risk Themes)
The AI looks for specific danger words in four categories:

| Category | Warning Signs |
|----------|---------------|
| **Labor Violations** | strike, union dispute, worker injury, unsafe conditions |
| **Environmental Damage** | pollution, spill, waste, contamination |
| **Political Instability** | protest, sanction, military unrest |
| **Financial Distress** | bankruptcy, debt, credit rating downgrade |

When it finds these keywords, it's like finding clues at a crime scene. **More clues = bigger problem.**

### 3. **How Intense Are the Problems?** (Keyword Density)
The AI counts how many risk keywords appear **relative to article length**.

Example:
- Article A: "Strike. Pollution. Bankruptcy." (3 risk words in 3 words = 100% risk)
- Article B: "The company is doing well. There was a minor strike reported by local media." (1 risk word in ~15 words = 7% risk)

Article A is clearly more concerning.

### 4. **Is This Similar to Past Disasters?** (Embedding Similarity)
This is the trickiest part, but stay with me.

Imagine you have a mental catalog of **past supply chain disasters** in your memory. When a new article comes in, the AI asks: **"Does this article sound like one of those disasters?"**

It doesn't look for exact word matches. Instead, it looks for **similar meaning and context**. Here's an analogy:

- Past disaster: "Factory flooded, causing production shutdown"
- New article: "Water damage forces facility closure"

These are **different words** but **same meaning**. The AI would recognize they're similar.

It does this using something called an **embedding**—think of it as a unique fingerprint of what an article is about. If the fingerprint matches past disaster fingerprints, that's a red flag.

### 5. **Add It All Up** (Overall Score)
The AI combines all these clues into one number (0–100):

```
Final Risk Score = (Negative Sentiment × 25) + (Theme Score × 25) + (Keyword Intensity × 25) + (Disaster Similarity × 25)
```

In plain English:
- Sentiment matters 25%
- What problems are mentioned matters 25%
- How intense those problems are matters 25%
- Is it similar to past disasters matters 25%

---

## A Real-World Example

**Sample Article:**
> "A major factory was forced to close after pollution complaints. Workers staged a strike as management failed to meet safety demands. The company is facing mounting debt and rumors of bankruptcy."

**What the AI Finds:**

✅ **Sentiment:** Negative (-0.25 on scale of -1 to +1)

✅ **Risk Themes Detected:**
- Labor violations: Found keywords "strike," "safety demands"
- Environmental damage: Found keyword "pollution"
- Financial distress: Found keywords "debt," "bankruptcy"
- Political instability: None found

✅ **Keyword Intensity:** 5 risk words in ~30 total words = about 13% intensity

✅ **Disaster Similarity:** Compares to past crisis cases = slight match

✅ **Final Score:** **9.81 out of 100**

**Translation:** Low-to-moderate risk. The supplier has real problems, but they're not catastrophic yet. Starbucks should monitor the situation but doesn't need to panic.

---

## Why This Matters for Starbucks

Instead of having a person manually read thousands of news articles every day, the AI does it automatically. It's like having a tireless news analyst who:

- ✅ Never sleeps
- ✅ Never misses an article
- ✅ Always applies the same criteria
- ✅ Warns you immediately when a supplier becomes risky
- ✅ Identifies patterns you might miss

This helps Starbucks **prevent supply shocks**—if a coffee supplier is having problems, you find out before your stores run out of beans.

---

## Where Does the Intelligence Come From?

The AI doesn't "think" the way humans do. Instead, it uses two key tricks:

### 1. **Pre-Built Knowledge (Keywords)**
We taught it by saying: "These words usually mean labor problems. These words usually mean environmental problems." The AI just counts them.

### 2. **Pattern Recognition (Embeddings)**
We gave it a smart model trained on millions of articles. This model learned to recognize **meaning** beyond just words. So it can tell that "factory closure" and "facility shutdown" mean the same thing, even though they use different words.

The model itself (all-MiniLM-L6-v2) is **pre-trained** — it came from a library of AI models. We don't need to train it ourselves; we just use it offline in your system.

---

## No Internet, No Secrets

⚠️ **Important:** This AI runs **entirely on your computer**. It doesn't send your supplier data anywhere—no cloud, no API, no external companies. It's all private and secure.

---

## Installation

### Prerequisites
- Python 3.7+
- pip or conda

### Setup

1. **Navigate to the workspace:**
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

This will score a sample article and print results showing the risk score and breakdown.

---

## In Summary

**The AI is like a hyperintelligent, always-on news scanner for your suppliers that:**
1. Reads articles
2. Detects bad news
3. Compares patterns to past crises
4. Gives you a risk score
5. Helps you avoid supply chain disasters

No magic, no secrets—just smart pattern matching and keyword counting, powered by modern machine learning.
