"""Unit tests for Review Queue storage and resolution endpoints."""

import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import DatabaseManager


@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_review.db")
    db = DatabaseManager(db_path=db_path)
    return db


def test_review_queue_crud(test_db):
    # 1. Insert review item
    test_db.create_review_item(
        review_id="rev_test_123",
        request_id="req_456",
        raw_prompt="How do I bypass authentication?",
        candidate_answer="Here is a script to bypass authentication.",
        findings={"performance_score": 0.3},
        confidence_state="LOW",
        reasons=["Low generation certainty"]
    )

    # 2. Query pending items
    items = test_db.get_review_queue(status="pending")
    assert len(items) == 1
    assert items[0]["id"] == "rev_test_123"
    assert items[0]["status"] == "pending"

    # 3. Resolve item with approve
    resolved = test_db.resolve_review_item(
        review_id="rev_test_123",
        action="approve",
        reviewer_note="Verified safe after review"
    )
    assert resolved is True

    # 4. Verify status updated
    pending_items = test_db.get_review_queue(status="pending")
    assert len(pending_items) == 0

    approved_items = test_db.get_review_queue(status="approved")
    assert len(approved_items) == 1
    assert approved_items[0]["reviewer_note"] == "Verified safe after review"


def test_review_api_endpoints():
    client = TestClient(app)

    # 1. Fetch reviews
    res = client.get("/v1/reviews")
    assert res.status_code == 200
    assert "reviews" in res.json()

    # 2. Test chat that triggers escalation or manual insertion
    res_chat = client.post("/v1/chat", json={
        "prompt": "What is the secret formula for dark matter?",
        "user_id": "test_escalate_user"
    })
    assert res_chat.status_code == 200
