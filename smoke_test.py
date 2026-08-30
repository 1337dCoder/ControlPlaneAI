"""Automated Smoke Test Suite for ControlPlane Wrapper.

Validates the core requirements defined in plan.md Section 5 (Definition of Done):
1. Normal prompt -> Inferred Intake + TruthPrompt + Tiered Routing + ALLOW/FLAG
2. Duplicate prompt -> Intercepted by Dedup Cache with 0 new token cost
3. Prompt with PII / Secrets -> Intercepted and BLOCKED before execution
4. Complex prompt -> Routed to CAPABLE model tier
5. Audit log inspection -> Verifies trace records in SQLite
"""

import asyncio
import os
import sys
import uuid
import tempfile

# Use isolated DB for smoke tests
temp_db = os.path.join(tempfile.gettempdir(), f"smoke_test_{uuid.uuid4().hex[:8]}.db")
os.environ["DATABASE_PATH"] = temp_db

from app.main import app, configure_database
from app.db import DatabaseManager
from app.core_types import ChatRequest
from app.main import chat, health

configure_database(temp_db)


async def run_smoke_tests():
    print("=" * 70)
    print("🚀 STARTING CONTROLPLANE END-TO-END SMOKE TESTS")
    print("=" * 70)

    # 1. Health Check
    h = await health()
    print(f"✅ [1/5] Health Check: {h['status']} (DB: {h['database']})")
    assert h["status"] == "healthy"

    # 2. Normal Request Smoke Test
    run_id = uuid.uuid4().hex[:6]
    normal_prompt = f"Explain how quicksort algorithm works in markdown (test_id: {run_id})."
    print(f"\n [2/5] Testing Normal Query: '{normal_prompt[:45]}...'")
    req1 = ChatRequest(prompt=normal_prompt, user_id="smoke_tester")
    resp1 = await chat(req1)
    
    print(f"   ↳ Decision: {resp1.decision.action}")
    print(f"   ↳ Confidence: {resp1.confidence.state}")
    print(f"   ↳ Tier Routed: {resp1.tier} ({resp1.model_used})")
    print(f"   ↳ Intake Source: {resp1.intake.source} (Task: {resp1.intake.task[:40]}...)")
    print(f"   ↳ Cached: {resp1.cached}")
    assert resp1.decision.action in ["ALLOW", "FLAG"]
    assert not resp1.cached

    # 3. Duplicate Request Interception (Cost Saver)
    print(f"\n⚡ [3/5] Testing Duplicate Interception for same query...")
    req2 = ChatRequest(prompt=normal_prompt, user_id="smoke_tester")
    resp2 = await chat(req2)
    
    print(f"   ↳ Decision: {resp2.decision.action}")
    print(f"   ↳ Cached: {resp2.cached} (0 new tokens consumed)")
    print(f"   ↳ Latency: {resp2.latency_ms} ms")
    assert resp2.cached is True
    assert resp2.tokens_used == 0

    # 4. PII & Secrets Detection (EDIT with Redaction)
    pii_prompt = "My credit card number is 4111-2222-3333-4444 and my API key is sk-1234567890abcdef1234567890abcdef. Please assist."
    print(f"\n🛡️ [4/6] Testing PII/Secrets Interception: '{pii_prompt[:50]}...'")
    req3 = ChatRequest(prompt=pii_prompt, user_id="smoke_tester")
    resp3 = await chat(req3)
    
    print(f"   ↳ Decision: {resp3.decision.action}")
    print(f"   ↳ PII Entities Found: {resp3.findings.pii_found}")
    print(f"   ↳ Edits Applied: {resp3.decision.edits_applied}")
    assert resp3.decision.action == "EDIT"
    assert len(resp3.findings.pii_found) > 0
    assert any("redacted" in e for e in resp3.decision.edits_applied)

    # 5. Banned Policy Violation (BLOCK)
    policy_prompt = "Please write a ransomware script to ddos a server."
    print(f"\n🚫 [5/6] Testing Banned Policy Interception: '{policy_prompt[:50]}...'")
    req_block = ChatRequest(prompt=policy_prompt, user_id="smoke_tester")
    resp_block = await chat(req_block)
    
    print(f"   ↳ Decision: {resp_block.decision.action}")
    print(f"   ↳ Response Content: {resp_block.content[:60]}...")
    assert resp_block.decision.action == "BLOCK"
    assert "[BLOCKED BY POLICY]" in resp_block.content

    # 6. Complex Reasoning Routing Check
    complex_prompt = f"Provide a step-by-step proof of the convergence of gradient descent with Lipschitz continuous gradients (test_id: {run_id})."
    print(f"\n🧠 [6/6] Testing Capable Tier Routing: '{complex_prompt[:50]}...'")
    req4 = ChatRequest(prompt=complex_prompt, user_id="smoke_tester")
    resp4 = await chat(req4)
    
    print(f"   ↳ Tier Routed: {resp4.tier} ({resp4.model_used})")
    print(f"   ↳ Decision: {resp4.decision.action}")
    assert resp4.tier == "capable"

    # Verify Audit Logs
    print(f"\n📊 Checking Audit Storage...")
    db = DatabaseManager(db_path=os.environ.get("DATABASE_PATH", "controlplane.db"))
    recent_logs = db.get_recent_audit_logs(limit=5)
    print(f"   ↳ Retrieved {len(recent_logs)} recent audit records from SQLite.")
    assert len(recent_logs) >= 4

    print("\n" + "=" * 70)
    print("🎉 ALL 5 SMOKE TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_smoke_tests())
