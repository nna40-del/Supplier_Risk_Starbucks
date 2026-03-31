"""Database module for storing and retrieving news article data and scoring results."""

import sqlite3
import json
from typing import Dict, List, Any, Optional
from datetime import datetime


class NewsDatabase:
    """SQLite database for managing news articles and their risk assessments."""

    def __init__(self, db_path: str = "news_articles.db"):
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

        # News articles table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                content TEXT NOT NULL,
                content_length INTEGER,
                supplier_name TEXT,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # ensure column exists for older databases
        cursor.execute("PRAGMA table_info(news_articles)")
        existing = [row[1] for row in cursor.fetchall()]
        if "supplier_name" not in existing:
            cursor.execute("ALTER TABLE news_articles ADD COLUMN supplier_name TEXT")

        # News scoring results table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news_scoring_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL,
                overall_risk_score REAL,
                risk_level TEXT,
                sentiment_score REAL,
                keyword_intensity_score REAL,
                disruption_similarity_score REAL,
                theme_scores JSON,
                full_results JSON,
                scored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (article_id) REFERENCES news_articles(id)
            )
        """)

        conn.commit()
        conn.close()

    def save_article(
        self, filename: str, content: str, supplier_name: Optional[str] = None
    ) -> int:
        """
        Save a news article to the database.

        Args:
            filename: Name of the file
            content: Text content of the article
            supplier_name: Optional supplier name associated with article

        Returns:
            Article ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        content_length = len(content)

        cursor.execute(
            """
            INSERT INTO news_articles (filename, content, content_length, supplier_name)
            VALUES (?, ?, ?, ?)
        """,
            (filename, content, content_length, supplier_name),
        )

        conn.commit()
        cursor.execute("SELECT last_insert_rowid()")
        article_id = cursor.fetchone()[0]
        conn.close()

        return article_id

    def save_scoring_result(
        self,
        article_id: int,
        overall_risk_score: float,
        risk_level: str,
        sentiment_score: float,
        keyword_intensity_score: float,
        disruption_similarity_score: float,
        theme_scores: Dict[str, float],
        full_results: Dict[str, Any],
    ) -> int:
        """
        Save a news scoring result.

        Args:
            article_id: ID of the article
            overall_risk_score: Overall risk score (0-100)
            risk_level: Risk level (LOW, MODERATE, HIGH, SEVERE)
            sentiment_score: Sentiment score
            keyword_intensity_score: Keyword intensity score
            disruption_similarity_score: Disruption similarity score
            theme_scores: Dictionary of theme scores
            full_results: Complete scoring results JSON

        Returns:
            Scoring result ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        theme_scores_json = json.dumps(theme_scores)
        full_results_json = json.dumps(full_results)

        cursor.execute(
            """
            INSERT INTO news_scoring_results 
            (article_id, overall_risk_score, risk_level, sentiment_score, 
             keyword_intensity_score, disruption_similarity_score, theme_scores, full_results)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                article_id,
                overall_risk_score,
                risk_level,
                sentiment_score,
                keyword_intensity_score,
                disruption_similarity_score,
                theme_scores_json,
                full_results_json,
            ),
        )

        conn.commit()
        cursor.execute("SELECT last_insert_rowid()")
        result_id = cursor.fetchone()[0]
        conn.close()

        return result_id

    def get_article(self, article_id: int) -> Optional[Dict[str, Any]]:
        """Get a news article by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM news_articles WHERE id = ?", (article_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return dict(row)

    def get_all_articles(self) -> List[Dict[str, Any]]:
        """Get all news articles."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM news_articles ORDER BY uploaded_at DESC")
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_article_with_latest_score(
        self, article_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get an article with its latest scoring result."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT a.*, s.* 
            FROM news_articles a
            LEFT JOIN news_scoring_results s ON a.id = s.article_id
            WHERE a.id = ?
            ORDER BY s.scored_at DESC
            LIMIT 1
        """,
            (article_id,),
        )

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return dict(row)

    def get_scoring_result(self, result_id: int) -> Optional[Dict[str, Any]]:
        """Get a scoring result by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM news_scoring_results WHERE id = ?", (result_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return dict(row)

    def get_scoring_results_for_article(self, article_id: int) -> List[Dict[str, Any]]:
        """Get all scoring results for an article."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM news_scoring_results WHERE article_id = ? ORDER BY scored_at DESC",
            (article_id,),
        )
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_articles_by_supplier(self, supplier_name: str) -> List[Dict[str, Any]]:
        """Retrieve articles linked to a particular supplier."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM news_articles WHERE supplier_name = ? ORDER BY uploaded_at DESC",
            (supplier_name,),
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_supplier_news_stats(self) -> Dict[str, Any]:
        """Compute aggregated news-risk statistics per supplier."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Get all distinct suppliers with articles
        cursor.execute("""
            SELECT DISTINCT a.supplier_name
            FROM news_articles a
            WHERE a.supplier_name IS NOT NULL
            ORDER BY a.supplier_name
        """)
        suppliers = cursor.fetchall()
        result = {}

        for supplier_row in suppliers:
            supplier_name = supplier_row["supplier_name"]

            # Count articles for this supplier
            cursor.execute(
                "SELECT COUNT(*) FROM news_articles WHERE supplier_name = ?",
                (supplier_name,),
            )
            article_count = cursor.fetchone()[0]

            # Get  scores for articles from this supplier
            cursor.execute(
                """
                SELECT s.overall_risk_score
                FROM news_articles a
                LEFT JOIN news_scoring_results s ON a.id = s.article_id
                WHERE a.supplier_name = ?
                AND s.overall_risk_score IS NOT NULL
                ORDER BY s.overall_risk_score DESC
            """,
                (supplier_name,),
            )

            scores_list = [row["overall_risk_score"] for row in cursor.fetchall()]

            if scores_list:
                avg_score = sum(scores_list) / len(scores_list)
                max_score = max(scores_list)
            else:
                avg_score = 0.0
                max_score = 0.0

            result[supplier_name] = {
                "count": article_count,
                "avg_score": avg_score,
                "max_score": max_score,
            }

        conn.close()
        return result

    def get_articles_by_risk_level(self, risk_level: str) -> List[Dict[str, Any]]:
        """Get articles by their latest risk level."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT a.* FROM news_articles a
            INNER JOIN (
                SELECT article_id, MAX(scored_at) as latest_score
                FROM news_scoring_results
                GROUP BY article_id
            ) latest ON a.id = latest.article_id
            INNER JOIN news_scoring_results s ON a.id = s.article_id AND s.scored_at = latest.latest_score
            WHERE s.risk_level = ?
            ORDER BY a.uploaded_at DESC
        """,
            (risk_level,),
        )
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def delete_article(self, article_id: int) -> bool:
        """Delete an article and all its scoring results."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "DELETE FROM news_scoring_results WHERE article_id = ?", (article_id,)
        )
        cursor.execute("DELETE FROM news_articles WHERE id = ?", (article_id,))

        conn.commit()
        affected = cursor.rowcount
        conn.close()

        return affected > 0

    def delete_articles_batch(self, article_ids: List[int]) -> int:
        """Delete multiple articles and their scoring results."""
        conn = self._get_connection()
        cursor = conn.cursor()

        deleted_count = 0
        for article_id in article_ids:
            cursor.execute(
                "DELETE FROM news_scoring_results WHERE article_id = ?", (article_id,)
            )
            cursor.execute("DELETE FROM news_articles WHERE id = ?", (article_id,))
            deleted_count += 1

        conn.commit()
        conn.close()

        return deleted_count

    def get_summary_stats(self) -> Dict[str, Any]:
        """Get database summary statistics."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Total articles
        cursor.execute("SELECT COUNT(*) as total FROM news_articles")
        total = cursor.fetchone()["total"]

        # Risk distribution (from latest scores)
        cursor.execute("""
            SELECT risk_level, COUNT(*) as count
            FROM news_scoring_results
            WHERE id IN (
                SELECT MAX(id)
                FROM news_scoring_results
                GROUP BY article_id
            )
            GROUP BY risk_level
        """)
        risk_dist = {row["risk_level"]: row["count"] for row in cursor.fetchall()}

        # Average risk score
        cursor.execute("""
            SELECT AVG(overall_risk_score) as avg_score
            FROM news_scoring_results
            WHERE id IN (
                SELECT MAX(id)
                FROM news_scoring_results
                GROUP BY article_id
            )
        """)
        avg_score = cursor.fetchone()["avg_score"] or 0

        # Average sentiment score
        cursor.execute("""
            SELECT AVG(sentiment_score) as avg_sentiment
            FROM news_scoring_results
            WHERE id IN (
                SELECT MAX(id)
                FROM news_scoring_results
                GROUP BY article_id
            )
        """)
        avg_sentiment = cursor.fetchone()["avg_sentiment"] or 0

        conn.close()

        return {
            "total_articles": total,
            "risk_distribution": risk_dist,
            "average_risk_score": round(avg_score, 2),
            "average_sentiment_score": round(avg_sentiment, 3),
        }

    def search_articles(self, keyword: str) -> List[Dict[str, Any]]:
        """
        Search articles by keyword in filename or content.

        Args:
            keyword: Search keyword

        Returns:
            List of matching articles
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        search_term = f"%{keyword}%"
        cursor.execute(
            """
            SELECT * FROM news_articles
            WHERE filename LIKE ? OR content LIKE ?
            ORDER BY uploaded_at DESC
        """,
            (search_term, search_term),
        )
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]
