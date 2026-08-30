"""Stage 2b: Cost & Dedup Detector.

Handles exact and semantic deduplication interception and rolling spend velocity anomaly tracking.
"""

import hashlib
import re
import math
from typing import Dict, Any, Optional, Tuple, List
from collections import Counter
from app.db import DatabaseManager


class CostDetector:
    """Detects repeated / semantically equivalent queries and flags spending rate anomalies."""

    def __init__(self, db: DatabaseManager, policy_config: Dict[str, Any] = None):
        self.db = db
        self.policy = policy_config or {}
        cost_cfg = self.policy.get("cost_controls", {})
        self.hourly_limit = cost_cfg.get("spend_velocity_hourly_limit_usd", 10.00)
        self.single_request_limit = cost_cfg.get("single_request_cost_warning_usd", 0.50)
        self.similarity_threshold = cost_cfg.get("dedup_similarity_threshold", 0.82)

    def normalize_for_hash(self, text: str) -> str:
        """Normalize whitespace, punctuation, and lowercase for exact dedup hashing."""
        cleaned = re.sub(r"[^\w\s]", "", text.strip().lower())
        cleaned = re.sub(r"\s+", " ", cleaned)
        return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()

    def _get_char_ngrams(self, text: str, n: int = 3) -> Counter:
        """Extract character n-grams from text for robust semantic similarity matching."""
        cleaned = re.sub(r"\s+", " ", text.strip().lower())
        if len(cleaned) < n:
            return Counter([cleaned])
        return Counter([cleaned[i:i+n] for i in range(len(cleaned) - n + 1)])

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate cosine similarity between two text strings using n-gram vector frequencies."""
        vec1 = self._get_char_ngrams(text1)
        vec2 = self._get_char_ngrams(text2)

        intersection = set(vec1.keys()) & set(vec2.keys())
        if not intersection:
            return 0.0

        dot_product = sum(vec1[k] * vec2[k] for k in intersection)
        mag1 = math.sqrt(sum(v * v for v in vec1.values()))
        mag2 = math.sqrt(sum(v * v for v in vec2.values()))

        if mag1 == 0 or mag2 == 0:
            return 0.0

        return round(dot_product / (mag1 * mag2), 4)

    def check_dedup(self, prompt: str) -> Tuple[bool, Optional[str]]:
        """
        Check if query is an exact or semantic duplicate in the recent cache.
        Returns (is_duplicate, cached_response_text).
        """
        # 1. Fast exact normalized hash lookup
        prompt_hash = self.normalize_for_hash(prompt)
        cached_entry = self.db.get_cached_dedup(prompt_hash)
        if cached_entry:
            return True, cached_entry.get("response_text")

        # 2. Semantic similarity scan over recent queries
        recent_records = self.db.get_all_recent_dedup_records(max_age_seconds=86400)
        for record in recent_records:
            cached_prompt = record.get("raw_prompt", "")
            sim = self.calculate_similarity(prompt, cached_prompt)
            if sim >= self.similarity_threshold:
                return True, record.get("response_text")

        return False, None

    def record_and_check_spend_anomaly(self, cost_usd: float) -> bool:
        """
        Check if this request or the rolling 1-hour spend exceeds safety thresholds.
        Returns True if an anomaly is detected.
        """
        if cost_usd > self.single_request_limit:
            return True
            
        rolling_hourly_spend = self.db.get_recent_spend_total(window_minutes=60)
        if (rolling_hourly_spend + cost_usd) > self.hourly_limit:
            return True
            
        return False
