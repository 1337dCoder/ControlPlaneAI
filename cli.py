"""ControlPlane Interactive CLI Tool.

Enables interactive testing, demo runs, and SQLite audit inspection from the terminal.

Usage:
    python cli.py               # Interactive Chat Mode
    python cli.py demo          # Run the 3 canonical smoke demo tests
    python cli.py audit         # Inspect recent SQLite audit traces
"""

import sys
import os
import json
import asyncio
from app.main import chat, health
from app.core_types import ChatRequest
from app.db import DatabaseManager


async def interactive_mode():
    print("=" * 65)
    print("🎮 CONTROLPLANE WRAPPER — INTERACTIVE TERMINAL")
    print("Type your prompt and press Enter. Type 'exit' or 'quit' to stop.")
    print("=" * 65)

    user_id = "cli_user"
    while True:
        try:
            prompt = input("\n👤 User Prompt > ").strip()
            if not prompt:
                continue
            if prompt.lower() in ["exit", "quit", "q"]:
                print("Goodbye!")
                break

            req = ChatRequest(prompt=prompt, user_id=user_id)
            resp = await chat(req)

            print("\n" + "-" * 50)
            print(f"🎯 DECISION:    {resp.decision.action}")
            print(f"📊 CONFIDENCE:  {resp.confidence.state} (Score: {resp.findings.performance_score or resp.findings.self_rated_confidence})")
            print(f"🔀 TIER / MODEL: {resp.tier.upper()} ({resp.model_used})")
            print(f"⚡ CACHE HIT:   {'YES (0 tokens)' if resp.cached else 'NO'}")
            print(f"⏱️ LATENCY:     {resp.latency_ms} ms")
            if resp.findings.pii_found:
                print(f"🛡️ PII FOUND:    {', '.join(resp.findings.pii_found)}")
            if resp.findings.policy_hits:
                print(f"⚠️ POLICY HITS: {', '.join(resp.findings.policy_hits)}")
            print("-" * 50)
            print("💬 RESPONSE:")
            print(resp.content)
            print("-" * 50)

        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break


async def demo_mode():
    from smoke_test import run_smoke_tests
    await run_smoke_tests()


def audit_mode(limit: int = 10):
    db_path = os.environ.get("DATABASE_PATH", "controlplane.db")
    db = DatabaseManager(db_path=db_path)
    logs = db.get_recent_audit_logs(limit=limit)

    print("=" * 80)
    print(f"📋 RECENT AUDIT TRACES (SQLite: {db_path}) — Last {len(logs)} Records")
    print("=" * 80)

    if not logs:
        print("No audit logs found.")
        return

    for i, log in enumerate(logs, 1):
        print(f"\n[{i}] Request ID: {log['request_id']} | Timestamp: {log['timestamp']}")
        print(f"    User: {log['user_id']} | Action: {log['decision_action']} | Conf: {log['confidence_state']}")
        print(f"    Tier: {log['model_tier']} ({log['model_name']}) | Latency: {log['latency_ms']} ms | Cached: {bool(log['cached'])}")
        print(f"    Prompt: {log['raw_prompt'][:70]}...")
        reasons = json.loads(log['decision_reasons']) if isinstance(log['decision_reasons'], str) else log['decision_reasons']
        print(f"    Reasons: {'; '.join(reasons)}")


def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg == "demo":
            asyncio.run(demo_mode())
            return
        elif arg == "audit":
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
            audit_mode(limit)
            return

    asyncio.run(interactive_mode())


if __name__ == "__main__":
    main()
