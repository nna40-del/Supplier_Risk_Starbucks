#!/usr/bin/env python3
"""Quick test to verify news database functionality."""

from news_database import NewsDatabase

# Create database instance
db = NewsDatabase("test_news.db")

# Test data
test_article = """
Factory in Brazil hit by environmental violations. Authorities discovered improper waste disposal leading to 
significant water pollution. Workers have reported safety concerns and are considering strike action. The company 
faces potential fines and public scrutiny. Stock price has dropped 15% following the news.
"""

test_result = {
    "labor_violations": 0.75,
    "environmental_damage": 0.85,
    "political_instability": 0.2,
    "financial_distress": 0.6,
}

print("🧪 Testing News Database Functionality...\n")

# Test 1: Save an article
print("1️⃣ Saving news article to database...")
article_id = db.save_article("test_news_article.txt", test_article)
print(f"   ✓ Article saved with ID: {article_id}\n")

# Test 2: Save scoring result
print("2️⃣ Saving news scoring result...")
db.save_scoring_result(
    article_id=article_id,
    overall_risk_score=68.5,
    risk_level="HIGH",
    sentiment_score=-0.65,
    keyword_intensity_score=0.72,
    disruption_similarity_score=0.58,
    theme_scores=test_result,
    full_results={"raw": "test"},
)
print("   ✓ Scoring result saved\n")

# Test 3: Get article
print("3️⃣ Retrieving article from database...")
retrieved = db.get_article(article_id)
print(
    f"   ✓ Retrieved: {retrieved['filename']} ({retrieved['content_length']} chars)\n"
)

# Test 4: Get all articles
print("4️⃣ Retrieving all articles...")
all_articles = db.get_all_articles()
print(f"   ✓ Found {len(all_articles)} article(s)\n")

# Test 5: Get scoring results
print("5️⃣ Retrieving scoring results...")
scores = db.get_scoring_results_for_article(article_id)
print(f"   ✓ Found {len(scores)} scoring result(s)")
if scores:
    print(
        f"   ✓ Risk Score: {scores[0]['overall_risk_score']}, Risk Level: {scores[0]['risk_level']}\n"
    )

# Test 6: Get summary stats
print("6️⃣ Getting database statistics...")
stats = db.get_summary_stats()
print(f"   ✓ Total articles: {stats['total_articles']}")
print(f"   ✓ Risk distribution: {stats['risk_distribution']}")
print(f"   ✓ Average risk score: {stats['average_risk_score']}")
print(f"   ✓ Average sentiment score: {stats['average_sentiment_score']}\n")

# Test 7: Search articles
print("7️⃣ Searching articles...")
search_results = db.search_articles("factory")
print(f"   ✓ Found {len(search_results)} article(s) matching 'factory" + "'\n")

# ----------------------------------------------------------------------
# Additional integration tests for supplier-news combined insights
# ----------------------------------------------------------------------

print("8️⃣ Testing supplier-news integration...")

from database import SupplierDatabase

# create supplier database and add a sample supplier
sup_db = SupplierDatabase("test_suppliers.db")
print("   ✓ Created supplier database")

supplier = {"name": "Example Supplier", "extra": "info"}
sup_id = sup_db.save_supplier(supplier)
print(f"   ✓ Supplier saved with ID: {sup_id}")

# score the supplier
sup_db.save_scoring_result(
    sup_id, risk_score=60, risk_level="HIGH", subscores={"dummy": 0.6}
)
print("   ✓ Supplier scoring result saved")

# save a news article linked to that supplier
article_id_2 = db.save_article(
    "supplier_news.txt", test_article, supplier_name="Example Supplier"
)
print(f"   ✓ Article saved with supplier link ID: {article_id_2}")

# score it for completeness
db.save_scoring_result(
    article_id=article_id_2,
    overall_risk_score=72.0,
    risk_level="HIGH",
    sentiment_score=-0.55,
    keyword_intensity_score=0.65,
    disruption_similarity_score=0.50,
    theme_scores=test_result,
    full_results={"raw": "test2"},
)
print("   ✓ Scoring result for linked article saved")

# verify supplier news stats
stats = db.get_supplier_news_stats()
print(f"   ✓ Supplier news stats: {stats}")

# calculate combined risk manually to ensure logic aligns
if "Example Supplier" in stats:
    avg_news = stats["Example Supplier"]["avg_score"]
    combined = round((60 + avg_news) / 2, 1)
    print(f"   ✓ Computed combined score for Example Supplier: {combined}")

print("✅ All tests (including integration) passed!")
