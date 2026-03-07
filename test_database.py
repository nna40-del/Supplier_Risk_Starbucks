#!/usr/bin/env python3
"""Quick test to verify database functionality."""

import json
from database import SupplierDatabase

# Create database instance
db = SupplierDatabase("test_suppliers.db")

# Test data
test_supplier = {
    "name": "Test Supplier Inc",
    "foodSafetyQuality": {
        "gfsCertification": "SQF Level 3",
        "lastAudit": "2025-06",
        "recallHistory": "None in last 5 years"
    },
    "regulatoryCompliance": {
        "fdaInspections": "No 483s",
        "supplierCodeOfConduct": "Signed"
    },
    "operationalReliability": {
        "otif": "97%",
        "leadTime": "7–10 days"
    },
    "financialStability": {
        "creditRisk": "Low",
        "revenueTrend": "Stable"
    }
}

print("🧪 Testing Database Functionality...\n")

# Test 1: Save a supplier
print("1️⃣ Saving supplier to database...")
supplier_id = db.save_supplier(test_supplier)
print(f"   ✓ Supplier saved with ID: {supplier_id}\n")

# Test 2: Save scoring result
print("2️⃣ Saving scoring result...")
db.save_scoring_result(
    supplier_id=supplier_id,
    risk_score=35,
    risk_level="MODERATE",
    subscores={
        "foodSafety": 0.45,
        "regulatory": 0.35,
        "operational": 0.25,
        "financial": 0.40
    }
)
print("   ✓ Scoring result saved\n")

# Test 3: Get supplier
print("3️⃣ Retrieving supplier from database...")
retrieved = db.get_supplier(supplier_id)
print(f"   ✓ Retrieved: {retrieved['name']} (Risk Level: {retrieved['risk_level']})\n")

# Test 4: Get all suppliers
print("4️⃣ Retrieving all suppliers...")
all_suppliers = db.get_all_suppliers()
print(f"   ✓ Found {len(all_suppliers)} supplier(s)\n")

# Test 5: Get summary stats
print("5️⃣ Getting database statistics...")
stats = db.get_summary_stats()
print(f"   ✓ Total suppliers: {stats['total_suppliers']}")
print(f"   ✓ Risk distribution: {stats['risk_distribution']}")
print(f"   ✓ Average risk score: {stats['average_risk_score']}\n")

print("✅ All tests passed! Database is working correctly.")
