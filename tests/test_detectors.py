"""Unit tests for Stage 2 Detectors (Performance, Cost, Responsibility)."""

import os
import pytest
from app.detectors.performance import PerformanceDetector
from app.detectors.responsibility import ResponsibilityDetector
from app.detectors.cost import CostDetector
from app.db import DatabaseManager


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_controlplane.db"
    return DatabaseManager(db_path=str(db_file))


def test_performance_detector_logprobs():
    detector = PerformanceDetector()
    text = "The capital of France is Paris."
    logprobs = [-0.01, -0.02, -0.01]  # High confidence
    score, self_rated = detector.evaluate(text, token_logprobs=logprobs)

    assert score is not None
    assert score >= 0.90


def test_performance_detector_self_rated_fallback():
    detector = PerformanceDetector()
    text = "Here is the calculation.\n[CONFIDENCE: 0.88]"
    score, self_rated = detector.evaluate(text, token_logprobs=None)

    assert score == 0.88
    assert self_rated == 0.88


def test_responsibility_detector_pii_detection():
    detector = ResponsibilityDetector()
    text = "Contact the admin at support@example.com or call 555-123-4567."
    pii = detector.scan_pii(text)

    assert "email" in pii
    assert "phone" in pii


def test_responsibility_detector_clean_text():
    detector = ResponsibilityDetector()
    text = "Binary search runs in O(log n) logarithmic time complexity."
    pii, policy_hits = detector.scan_all(text)

    assert len(pii) == 0
    assert len(policy_hits) == 0


def test_cost_detector_dedup_cache(test_db):
    detector = CostDetector(db=test_db)
    prompt = "Explain quantum entanglement in simple terms"
    prompt_hash = detector.normalize_for_hash(prompt)

    # Initially not in cache
    is_dup, cached = detector.check_dedup(prompt)
    assert not is_dup
    assert cached is None

    # Save to cache
    test_db.save_dedup_cache(prompt_hash, prompt, "Entanglement is a phenomenon...")

    # Now should hit cache
    is_dup2, cached2 = detector.check_dedup(prompt)
    assert is_dup2
    assert cached2 == "Entanglement is a phenomenon..."


def test_cost_detector_semantic_similarity_matching(test_db):
    detector = CostDetector(db=test_db)
    original_prompt = "What is the time complexity of binary search?"
    similar_prompt = "what is the time complexity of the binary search algorithm?"
    
    # Save original to cache
    orig_hash = detector.normalize_for_hash(original_prompt)
    test_db.save_dedup_cache(orig_hash, original_prompt, "Binary search is O(log n).")

    # Check similarity computation
    sim = detector.calculate_similarity(original_prompt, similar_prompt)
    assert sim >= 0.82

    # Check dedup interception for the similar prompt
    is_dup, cached = detector.check_dedup(similar_prompt)
    assert is_dup is True
    assert cached == "Binary search is O(log n)."

