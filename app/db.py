"""SQLite Storage Manager for ControlPlane.

Stores audit logs, semantic/hash dedup cache, and rolling spend records with zero external ops.
"""

import sqlite3
import json
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone


class DatabaseManager:
    """Manages local SQLite database operations."""

    def __init__(self, db_path: str = "controlplane.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initialize database schema tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Audit Logs Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    request_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    user_id TEXT,
                    raw_prompt TEXT,
                    normalized_intake TEXT,
                    truth_prompt_version TEXT,
                    model_tier TEXT,
                    model_name TEXT,
                    findings TEXT,
                    confidence_state TEXT,
                    decision_action TEXT,
                    decision_reasons TEXT,
                    tokens_used INTEGER,
                    estimated_cost_usd REAL,
                    latency_ms REAL,
                    cached INTEGER
                )
            """)

            # Dedup Cache Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dedup_cache (
                    prompt_hash TEXT PRIMARY KEY,
                    raw_prompt TEXT,
                    response_text TEXT,
                    created_at REAL
                )
            """)

            # Spend Records Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS spend_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT,
                    timestamp REAL,
                    cost_usd REAL,
                    tokens_used INTEGER
                )
            """)

            # Review Queue Table (Escalations)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS review_queue (
                    id TEXT PRIMARY KEY,
                    request_id TEXT,
                    raw_prompt TEXT,
                    candidate_answer TEXT,
                    findings TEXT,
                    confidence_state TEXT,
                    reasons TEXT,
                    status TEXT DEFAULT 'pending',
                    reviewer_note TEXT,
                    created_at TEXT,
                    resolved_at TEXT
                )
            """)
            conn.commit()

    def save_audit_log(self, record: Dict[str, Any]):
        """Persist a complete execution audit log entry."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO audit_logs (
                    request_id, timestamp, user_id, raw_prompt, normalized_intake,
                    truth_prompt_version, model_tier, model_name, findings,
                    confidence_state, decision_action, decision_reasons,
                    tokens_used, estimated_cost_usd, latency_ms, cached
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.get("request_id"),
                record.get("timestamp", datetime.now(timezone.utc).isoformat()),
                record.get("user_id", "anonymous"),
                record.get("raw_prompt", ""),
                json.dumps(record.get("normalized_intake", {})),
                record.get("truth_prompt_version", "truth_prompt_v1"),
                record.get("model_tier", "cheap"),
                record.get("model_name", ""),
                json.dumps(record.get("findings", {})),
                record.get("confidence_state", "QUALIFIED"),
                record.get("decision_action", "ALLOW"),
                json.dumps(record.get("decision_reasons", [])),
                record.get("tokens_used", 0),
                record.get("estimated_cost_usd", 0.0),
                record.get("latency_ms", 0.0),
                1 if record.get("cached") else 0
            ))
            conn.commit()

    def get_cached_dedup(self, prompt_hash: str, max_age_seconds: float = 86400) -> Optional[Dict[str, Any]]:
        """Retrieve cached response if within maximum age."""
        now = time.time()
        min_created_at = now - max_age_seconds
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT prompt_hash, raw_prompt, response_text, created_at
                FROM dedup_cache
                WHERE prompt_hash = ? AND created_at >= ?
            """, (prompt_hash, min_created_at))
            row = cursor.fetchone()
            if row:
                return dict(row)
        return None

    def get_all_recent_dedup_records(self, max_age_seconds: float = 86400) -> List[Dict[str, Any]]:
        """Retrieve all recent dedup records for semantic similarity scanning."""
        now = time.time()
        min_created_at = now - max_age_seconds
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT prompt_hash, raw_prompt, response_text, created_at
                FROM dedup_cache
                WHERE created_at >= ?
                ORDER BY created_at DESC
                LIMIT 200
            """, (min_created_at,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def save_dedup_cache(self, prompt_hash: str, raw_prompt: str, response_text: str):
        """Store prompt hash and generated response for future interception."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO dedup_cache (prompt_hash, raw_prompt, response_text, created_at)
                VALUES (?, ?, ?, ?)
            """, (prompt_hash, raw_prompt, response_text, time.time()))
            conn.commit()

    def record_spend(self, request_id: str, cost_usd: float, tokens_used: int):
        """Record spend entry for velocity and rate anomaly detection."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO spend_records (request_id, timestamp, cost_usd, tokens_used)
                VALUES (?, ?, ?, ?)
            """, (request_id, time.time(), cost_usd, tokens_used))
            conn.commit()

    def get_recent_spend_total(self, window_minutes: int = 60) -> float:
        """Calculate total spend in USD across recent rolling time window."""
        min_timestamp = time.time() - (window_minutes * 60)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT SUM(cost_usd) as total_spend
                FROM spend_records
                WHERE timestamp >= ?
            """, (min_timestamp,))
            row = cursor.fetchone()
            if row and row["total_spend"] is not None:
                return float(row["total_spend"])
        return 0.0

    def get_recent_audit_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent audit logs for debugging and inspection."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM audit_logs
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def create_review_item(
        self,
        review_id: str,
        request_id: str,
        raw_prompt: str,
        candidate_answer: str,
        findings: Dict[str, Any],
        confidence_state: str,
        reasons: List[str]
    ):
        """Insert a new escalation entry into the review queue."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO review_queue (
                    id, request_id, raw_prompt, candidate_answer, findings,
                    confidence_state, reasons, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """, (
                review_id,
                request_id,
                raw_prompt,
                candidate_answer,
                json.dumps(findings),
                confidence_state,
                json.dumps(reasons),
                datetime.now(timezone.utc).isoformat()
            ))
            conn.commit()

    def get_review_queue(self, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch review queue items, optionally filtered by status ('pending', 'approved', 'rejected')."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute("""
                    SELECT * FROM review_queue
                    WHERE status = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (status, limit))
            else:
                cursor.execute("""
                    SELECT * FROM review_queue
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,))
            rows = cursor.fetchall()
            results = []
            for row in rows:
                item = dict(row)
                try:
                    item["findings"] = json.loads(item["findings"])
                except Exception:
                    pass
                try:
                    item["reasons"] = json.loads(item["reasons"])
                except Exception:
                    pass
                results.append(item)
            return results

    def resolve_review_item(
        self,
        review_id: str,
        action: str,
        reviewer_note: str = ""
    ) -> bool:
        """Resolve a review queue item with approve, reject, or edit."""
        status_map = {
            "approve": "approved",
            "reject": "rejected",
            "edit": "edited"
        }
        status = status_map.get(action.lower(), "resolved")
        resolved_at = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE review_queue
                SET status = ?, reviewer_note = ?, resolved_at = ?
                WHERE id = ?
            """, (status, reviewer_note, resolved_at, review_id))
            conn.commit()
            return cursor.rowcount > 0
