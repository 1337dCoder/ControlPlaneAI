"""Storage Manager for ControlPlane.

Supports local SQLite (zero external ops) and Google Cloud Firestore / Firebase
for fully managed, real-time cloud storage in production.
"""

import os
import sqlite3
import json
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

# Optional Cloud Firestore Client
try:
    from google.cloud import firestore
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False


class DatabaseManager:
    """Manages database operations with automatic SQLite / Firebase Firestore switching."""

    def __init__(self, db_path: str = "controlplane.db", use_firestore: Optional[bool] = None):
        self.db_path = db_path
        
        # Check if Firestore should be enabled
        self.use_firestore = (
            use_firestore 
            if use_firestore is not None 
            else (os.environ.get("USE_FIRESTORE", "false").lower() in ("true", "1") or bool(os.environ.get("FIREBASE_PROJECT_ID")))
        )
        
        self.fs_client = None
        if self.use_firestore and FIRESTORE_AVAILABLE:
            try:
                project = os.environ.get("FIREBASE_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
                self.fs_client = firestore.Client(project=project) if project else firestore.Client()
                print(f"🔥 Connected to Firebase Cloud Firestore (Project: {self.fs_client.project})")
            except Exception as e:
                print(f"⚠️ Failed to connect to Firestore ({e}), falling back to SQLite at {self.db_path}")
                self.use_firestore = False

        if not self.use_firestore:
            self._init_sqlite_db()

    def _get_sqlite_connection(self) -> sqlite3.Connection:
        # Ensure parent directory exists (e.g. /tmp/ in serverless containers)
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir, exist_ok=True)
            except Exception:
                pass

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_sqlite_db(self):
        """Initialize SQLite database schema tables."""
        with self._get_sqlite_connection() as conn:
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

    # --- AUDIT LOGS ---

    def save_audit_log(self, record: Dict[str, Any]):
        """Persist a complete execution audit log entry."""
        if self.use_firestore and self.fs_client:
            try:
                doc_ref = self.fs_client.collection("audit_logs").document(record["request_id"])
                doc_ref.set(record)
                return
            except Exception as e:
                print(f"Firestore save_audit_log error: {e}")

        # SQLite Fallback
        with self._get_sqlite_connection() as conn:
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

    def get_recent_audit_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent audit logs."""
        if self.use_firestore and self.fs_client:
            try:
                query = self.fs_client.collection("audit_logs").order_by(
                    "timestamp", direction=firestore.Query.DESCENDING
                ).limit(limit)
                return [doc.to_dict() for doc in query.stream()]
            except Exception as e:
                print(f"Firestore get_recent_audit_logs error: {e}")

        # SQLite Fallback
        with self._get_sqlite_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM audit_logs
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    # --- DEDUP CACHE ---

    def get_cached_dedup(self, prompt_hash: str, max_age_seconds: float = 86400) -> Optional[Dict[str, Any]]:
        """Retrieve cached response if within maximum age."""
        now = time.time()
        min_created_at = now - max_age_seconds

        if self.use_firestore and self.fs_client:
            try:
                doc = self.fs_client.collection("dedup_cache").document(prompt_hash).get()
                if doc.exists:
                    data = doc.to_dict()
                    if data.get("created_at", 0) >= min_created_at:
                        return data
                return None
            except Exception as e:
                print(f"Firestore get_cached_dedup error: {e}")

        # SQLite Fallback
        with self._get_sqlite_connection() as conn:
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

        if self.use_firestore and self.fs_client:
            try:
                query = self.fs_client.collection("dedup_cache").where(
                    "created_at", ">=", min_created_at
                ).limit(200)
                return [doc.to_dict() for doc in query.stream()]
            except Exception as e:
                print(f"Firestore get_all_recent_dedup_records error: {e}")

        # SQLite Fallback
        with self._get_sqlite_connection() as conn:
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
        record = {
            "prompt_hash": prompt_hash,
            "raw_prompt": raw_prompt,
            "response_text": response_text,
            "created_at": time.time()
        }

        if self.use_firestore and self.fs_client:
            try:
                self.fs_client.collection("dedup_cache").document(prompt_hash).set(record)
                return
            except Exception as e:
                print(f"Firestore save_dedup_cache error: {e}")

        # SQLite Fallback
        with self._get_sqlite_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO dedup_cache (prompt_hash, raw_prompt, response_text, created_at)
                VALUES (?, ?, ?, ?)
            """, (prompt_hash, raw_prompt, response_text, record["created_at"]))
            conn.commit()

    # --- SPEND TRACKING ---

    def record_spend(self, request_id: str, cost_usd: float, tokens_used: int):
        """Record spend entry for velocity and rate anomaly detection."""
        spend_entry = {
            "request_id": request_id,
            "timestamp": time.time(),
            "cost_usd": cost_usd,
            "tokens_used": tokens_used
        }

        if self.use_firestore and self.fs_client:
            try:
                self.fs_client.collection("spend_records").add(spend_entry)
                return
            except Exception as e:
                print(f"Firestore record_spend error: {e}")

        # SQLite Fallback
        with self._get_sqlite_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO spend_records (request_id, timestamp, cost_usd, tokens_used)
                VALUES (?, ?, ?, ?)
            """, (request_id, spend_entry["timestamp"], cost_usd, tokens_used))
            conn.commit()

    def get_recent_spend_total(self, window_minutes: int = 60) -> float:
        """Calculate total spend in USD across recent rolling time window."""
        min_timestamp = time.time() - (window_minutes * 60)

        if self.use_firestore and self.fs_client:
            try:
                query = self.fs_client.collection("spend_records").where(
                    "timestamp", ">=", min_timestamp
                )
                total = sum(doc.to_dict().get("cost_usd", 0.0) for doc in query.stream())
                return float(total)
            except Exception as e:
                print(f"Firestore get_recent_spend_total error: {e}")

        # SQLite Fallback
        with self._get_sqlite_connection() as conn:
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

    # --- REVIEW QUEUE (HUMAN ESCALATIONS) ---

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
        item = {
            "id": review_id,
            "request_id": request_id,
            "raw_prompt": raw_prompt,
            "candidate_answer": candidate_answer,
            "findings": findings,
            "confidence_state": confidence_state,
            "reasons": reasons,
            "status": "pending",
            "reviewer_note": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "resolved_at": None
        }

        if self.use_firestore and self.fs_client:
            try:
                self.fs_client.collection("review_queue").document(review_id).set(item)
                return
            except Exception as e:
                print(f"Firestore create_review_item error: {e}")

        # SQLite Fallback
        with self._get_sqlite_connection() as conn:
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
                item["created_at"]
            ))
            conn.commit()

    def get_review_queue(self, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch review queue items, optionally filtered by status."""
        if self.use_firestore and self.fs_client:
            try:
                col = self.fs_client.collection("review_queue")
                if status:
                    query = col.where("status", "==", status).order_by(
                        "created_at", direction=firestore.Query.DESCENDING
                    ).limit(limit)
                else:
                    query = col.order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit)
                return [doc.to_dict() for doc in query.stream()]
            except Exception as e:
                print(f"Firestore get_review_queue error: {e}")

        # SQLite Fallback
        with self._get_sqlite_connection() as conn:
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

        if self.use_firestore and self.fs_client:
            try:
                doc_ref = self.fs_client.collection("review_queue").document(review_id)
                doc_ref.update({
                    "status": status,
                    "reviewer_note": reviewer_note,
                    "resolved_at": resolved_at
                })
                return True
            except Exception as e:
                print(f"Firestore resolve_review_item error: {e}")

        # SQLite Fallback
        with self._get_sqlite_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE review_queue
                SET status = ?, reviewer_note = ?, resolved_at = ?
                WHERE id = ?
            """, (status, reviewer_note, resolved_at, review_id))
            conn.commit()
            return cursor.rowcount > 0
