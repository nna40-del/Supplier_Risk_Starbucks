"""Database module for storing and retrieving supplier data."""

import sqlite3
import json
from typing import Dict, List, Any, Optional
from datetime import datetime


class SupplierDatabase:
    """SQLite database for managing supplier data."""

    def __init__(self, db_path: str = "suppliers.db"):
        """Initialize database connection and create tables if needed."""
        self.db_path = db_path
        self._init_tables()

    def _get_connection(self):
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self):
        """Create tables if they don't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Suppliers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                data JSON NOT NULL,
                risk_score INTEGER,
                risk_level TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Scoring history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scoring_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_id INTEGER NOT NULL,
                risk_score INTEGER,
                risk_level TEXT,
                subscores JSON,
                scored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
            )
        """)

        conn.commit()
        conn.close()

    def save_supplier(self, supplier: Dict[str, Any]) -> int:
        """
        Save a supplier to the database.

        Args:
            supplier: Dictionary with supplier data (must contain 'name' key)

        Returns:
            Supplier ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        name = supplier.get("name")
        if not name:
            raise ValueError("Supplier must have a 'name' field")

        supplier_json = json.dumps(supplier)

        try:
            cursor.execute(
                """
                INSERT INTO suppliers (name, data)
                VALUES (?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    data = excluded.data,
                    updated_at = CURRENT_TIMESTAMP
            """,
                (name, supplier_json),
            )
            conn.commit()

            # Get the supplier ID
            cursor.execute("SELECT id FROM suppliers WHERE name = ?", (name,))
            result = cursor.fetchone()
            supplier_id = result[0] if result else None

            conn.close()
            return supplier_id
        except Exception as e:
            conn.close()
            raise Exception(f"Error saving supplier: {str(e)}")

    def save_suppliers_batch(self, suppliers: List[Dict[str, Any]]) -> List[int]:
        """
        Save multiple suppliers to the database.

        Args:
            suppliers: List of supplier dictionaries

        Returns:
            List of supplier IDs
        """
        supplier_ids = []
        for supplier in suppliers:
            supplier_id = self.save_supplier(supplier)
            supplier_ids.append(supplier_id)
        return supplier_ids

    def save_scoring_result(
        self,
        supplier_id: int,
        risk_score: int,
        risk_level: str,
        subscores: Dict[str, float],
    ) -> int:
        """
        Save a scoring result for a supplier.

        Args:
            supplier_id: ID of the supplier
            risk_score: Calculated risk score (0-100)
            risk_level: Risk level (LOW, MODERATE, HIGH, SEVERE)
            subscores: Dictionary with component scores

        Returns:
            Scoring history ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        subscores_json = json.dumps(subscores)

        cursor.execute(
            """
            INSERT INTO scoring_history (supplier_id, risk_score, risk_level, subscores)
            VALUES (?, ?, ?, ?)
        """,
            (supplier_id, risk_score, risk_level, subscores_json),
        )

        # Update supplier's current risk score
        cursor.execute(
            """
            UPDATE suppliers
            SET risk_score = ?, risk_level = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """,
            (risk_score, risk_level, supplier_id),
        )

        conn.commit()
        cursor.execute("SELECT last_insert_rowid()")
        history_id = cursor.fetchone()[0]
        conn.close()

        return history_id

    def get_supplier(self, supplier_id: int) -> Optional[Dict[str, Any]]:
        """Get a supplier by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return dict(row)

    def get_supplier_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a supplier by name."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM suppliers WHERE name = ?", (name,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return dict(row)

    def get_all_suppliers(self) -> List[Dict[str, Any]]:
        """Get all suppliers."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM suppliers ORDER BY updated_at DESC")
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_suppliers_by_risk_level(self, risk_level: str) -> List[Dict[str, Any]]:
        """Get suppliers by risk level."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM suppliers WHERE risk_level = ? ORDER BY updated_at DESC",
            (risk_level,),
        )
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_scoring_history(self, supplier_id: int) -> List[Dict[str, Any]]:
        """Get scoring history for a supplier."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM scoring_history WHERE supplier_id = ? ORDER BY scored_at DESC",
            (supplier_id,),
        )
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def delete_supplier(self, supplier_id: int) -> bool:
        """Delete a supplier and their history."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "DELETE FROM scoring_history WHERE supplier_id = ?", (supplier_id,)
        )
        cursor.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))

        conn.commit()
        affected = cursor.rowcount
        conn.close()

        return affected > 0

    def get_summary_stats(self) -> Dict[str, Any]:
        """Get database summary statistics."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as total FROM suppliers")
        total = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT risk_level, COUNT(*) as count
            FROM suppliers
            WHERE risk_level IS NOT NULL
            GROUP BY risk_level
        """)
        risk_dist = {row["risk_level"]: row["count"] for row in cursor.fetchall()}

        cursor.execute(
            "SELECT AVG(risk_score) as avg_score FROM suppliers WHERE risk_score IS NOT NULL"
        )
        avg_score = cursor.fetchone()["avg_score"] or 0

        conn.close()

        return {
            "total_suppliers": total,
            "risk_distribution": risk_dist,
            "average_risk_score": round(avg_score, 2),
        }
