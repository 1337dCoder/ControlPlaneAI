"""FastAPI Application & Pipeline Orchestrator for ControlPlane Wrapper."""

import os
import uuid
try:
    import yaml
except ImportError:
    yaml = None
import time
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager

load_dotenv()

from app.core_types import (
    ChatRequest,
    ChatResponse,
    DetectionFindings,
    ConfidenceResult,
    Decision,
    IntakeResult,
    ReviewItem,
    ReviewResolution,
)
from app.truth_prompt import TruthPromptBuilder
from app.intake import IntakeNormalizer
from app.router import TieredRouter
from app.detectors.performance import PerformanceDetector
from app.detectors.cost import CostDetector
from app.detectors.responsibility import ResponsibilityDetector
from app.confidence import ConfidenceStateMachine
from app.decision import DecisionEngine
from app.providers import LLMProviderClient
from app.db import DatabaseManager

# Load policy.yaml
POLICY_PATH = Path(__file__).parent / "policy.yaml"

DEFAULT_FALLBACK_POLICY = {
    "model_tiers": {
        "cheap": {"default_model": "gpt-3.5-turbo", "cost_per_1k_input": 0.0005, "cost_per_1k_output": 0.0015},
        "capable": {"default_model": "gpt-4o", "cost_per_1k_input": 0.005, "cost_per_1k_output": 0.015}
    },
    "routing_triggers": {
        "capable_keywords": ["step-by-step proof", "mathematical proof", "formal verification", "security audit"],
        "max_prompt_length_for_cheap": 1200
    },
    "responsibility": {
        "pii_regex": {
            "email": r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
            "phone": r"(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}",
            "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
            "credit_card": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
            "api_key": r"\b(?:sk-[a-zA-Z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[a-zA-Z0-9]{36})\b"
        },
        "banned_topics": []
    },
    "confidence": {"high_threshold": 0.80, "qualified_threshold": 0.50, "default_threshold": 0.75},
    "cost_controls": {
        "dedup_cache_window_hours": 24,
        "dedup_similarity_threshold": 0.82,
        "spend_velocity_hourly_limit_usd": 10.00,
        "single_request_cost_warning_usd": 0.50
    }
}


def load_policy() -> Dict[str, Any]:
    if yaml and POLICY_PATH.exists():
        try:
            with open(POLICY_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or DEFAULT_FALLBACK_POLICY
        except Exception:
            return DEFAULT_FALLBACK_POLICY
    return DEFAULT_FALLBACK_POLICY


policy_config = load_policy()
db_path = os.environ.get("DATABASE_PATH", "controlplane.db")

# Initialize modules
db = DatabaseManager(db_path=db_path)
truth_prompt_builder = TruthPromptBuilder()
intake_normalizer = IntakeNormalizer()
router = TieredRouter(policy_config=policy_config)
performance_detector = PerformanceDetector(policy_config=policy_config)
cost_detector = CostDetector(db=db, policy_config=policy_config)
responsibility_detector = ResponsibilityDetector(policy_config=policy_config)
confidence_sm = ConfidenceStateMachine(policy_config=policy_config)
decision_engine = DecisionEngine(policy_config=policy_config)
provider_client = LLMProviderClient()


def configure_database(new_db_path: str):
    """Dynamically reconfigure database and cost detector."""
    global db, cost_detector, db_path
    db_path = new_db_path
    db = DatabaseManager(db_path=new_db_path)
    cost_detector = CostDetector(db=db, policy_config=policy_config)



@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    yield
    # Shutdown actions


from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="ControlPlane Wrapper API",
    description="Deterministic Prevention & Detection Proxy for LLMs",
    version="0.1.0",
    lifespan=lifespan
)

@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
@app.get("/dashboard")
async def dashboard():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(
            str(index_file),
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    return {"message": "ControlPlane API is running. Visit /health or POST /v1/chat"}


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "ControlPlane Wrapper",
        "version": "0.1.0",
        "database": db_path
    }


@app.get("/audit")
async def get_audit_logs(limit: int = 20):
    """Retrieve recent audit trace records."""
    return db.get_recent_audit_logs(limit=limit)


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Main proxy endpoint executing the 2-stage ControlPlane pipeline:
    Stage 1: Prevention (PII check -> Dedup check -> Intake -> TruthPrompt -> Router)
    Generation: Direct Provider Call
    Stage 2: Detection (Performance -> Cost -> Responsibility -> Confidence -> Decision -> Audit)
    """
    start_time = time.perf_counter()
    request_id = str(uuid.uuid4())
    raw_prompt = request.prompt

    # --- STAGE 1: PREVENTION ---

    # 1. Pre-execution responsibility scan on input prompt
    input_pii, input_policy_hits = responsibility_detector.scan_all(raw_prompt)
    if input_pii or input_policy_hits:
        findings = DetectionFindings(
            pii_found=input_pii,
            policy_hits=input_policy_hits,
            performance_score=0.0
        )
        conf = confidence_sm.evaluate(findings)
        decision = decision_engine.decide(conf, findings)
        
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        intake_stub = IntakeResult(task=raw_prompt[:50], source="inferred")

        # Persist audit record
        db.save_audit_log({
            "request_id": request_id,
            "user_id": request.user_id,
            "raw_prompt": raw_prompt,
            "normalized_intake": intake_stub.model_dump(),
            "truth_prompt_version": "truth_prompt_v1",
            "model_tier": "cheap",
            "model_name": "pre-execution-blocked",
            "findings": findings.model_dump(),
            "confidence_state": conf.state,
            "decision_action": decision.action,
            "decision_reasons": decision.reasons,
            "tokens_used": 0,
            "estimated_cost_usd": 0.0,
            "latency_ms": latency_ms,
            "cached": False
        })

        return ChatResponse(
            request_id=request_id,
            content=f"[BLOCKED BY POLICY]: {', '.join(decision.reasons)}",
            decision=decision,
            confidence=conf,
            findings=findings,
            intake=intake_stub,
            tier="cheap",
            model_used="pre-execution-check",
            cached=False,
            tokens_used=0,
            estimated_cost_usd=0.0,
            latency_ms=round(latency_ms, 2)
        )

    # 1.5 Clarification Interceptor (Only for genuinely ambiguous prompts like 1-2 vague words)
    is_clarification_response = request.metadata.get("is_clarification_response", False)
    words = raw_prompt.strip().split()
    vague_keywords = {"help", "code", "error", "bug", "fix", "test", "hi", "hello", "check"}
    is_genuinely_ambiguous = (
        not is_clarification_response and
        len(words) <= 2 and
        (len(words) == 1 or any(w.lower() in vague_keywords for w in words))
    )

    if is_genuinely_ambiguous:
        # Provide 4 distinct structured focus options with zero extra LLM calls
        options = [
            "1. High-level summary & core concept",
            "2. In-depth technical breakdown & inner workings",
            "3. Practical examples & real-world use cases",
            "4. Step-by-step guide & code implementation"
        ]
            
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        decision = Decision(
            action="ASK_USER",
            reasons=["Prompt is ambiguous; select your desired focus area"],
            clarifying_questions=options
        )
        conf = ConfidenceResult(state="LOW", reasons=["Single-word or underspecified prompt requires focus clarification"])
        findings = DetectionFindings(performance_score=0.0, is_duplicate=False)
        intake_stub = IntakeResult(task=raw_prompt[:50], source="inferred")
        
        return ChatResponse(
            request_id=request_id,
            content="Please choose how you would like this answered:",
            decision=decision,
            confidence=conf,
            findings=findings,
            intake=intake_stub,
            tier="cheap",
            model_used=router.cheap_model,
            cached=False,
            tokens_used=0,
            estimated_cost_usd=0.0,
            latency_ms=round(latency_ms, 2)
        )

    # 2. Dedup Cache Interception
    is_duplicate, cached_text = cost_detector.check_dedup(raw_prompt)
    if is_duplicate and cached_text:
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        intake_res = intake_normalizer.normalize(raw_prompt)
        findings = DetectionFindings(is_duplicate=True, performance_score=1.0)
        conf = ConfidenceResult(state="HIGH", reasons=["Served from verified dedup cache"])
        decision = Decision(action="ALLOW", reasons=["Cached response delivered (0 new tokens)"])

        # Persist audit record
        db.save_audit_log({
            "request_id": request_id,
            "user_id": request.user_id,
            "raw_prompt": raw_prompt,
            "normalized_intake": intake_res.model_dump(),
            "truth_prompt_version": "truth_prompt_v1",
            "model_tier": "cheap",
            "model_name": "cache-hit",
            "findings": findings.model_dump(),
            "confidence_state": conf.state,
            "decision_action": decision.action,
            "decision_reasons": decision.reasons,
            "tokens_used": 0,
            "estimated_cost_usd": 0.0,
            "latency_ms": latency_ms,
            "cached": True
        })

        return ChatResponse(
            request_id=request_id,
            content=cached_text,
            decision=decision,
            confidence=conf,
            findings=findings,
            intake=intake_res,
            tier="cheap",
            model_used="dedup-cache",
            cached=True,
            tokens_used=0,
            estimated_cost_usd=0.0,
            latency_ms=round(latency_ms, 2)
        )

    # 3. 4-Question Intake Normalization
    intake = intake_normalizer.normalize(raw_prompt)

    # 4. TruthPrompt System Envelope
    envelope = truth_prompt_builder.build_envelope(intake=intake)
    system_prompt = truth_prompt_builder.render_system_prompt(envelope)

    # 5. Tiered Model Routing
    tier, model_name, route_reason = router.route(
        raw_prompt=raw_prompt,
        intake=intake,
        model_override=request.model_override
    )

    # --- GENERATION ---
    llm_output = await provider_client.generate(
        system_prompt=system_prompt,
        user_prompt=raw_prompt,
        model_name=model_name
    )

    candidate_text = llm_output.get("content", "")
    token_logprobs = llm_output.get("logprobs", [])
    tokens_used = llm_output.get("tokens_used", 0)

    # Calculate estimated cost
    tier_pricing = policy_config.get("model_tiers", {}).get(tier, {})
    cost_rate = tier_pricing.get("cost_per_1k_output", 0.0015)
    estimated_cost = (tokens_used / 1000.0) * cost_rate

    # --- STAGE 2: DETECTION ---

    # 1. Performance & Confidence detection
    perf_score, self_rated_conf = performance_detector.evaluate(
        response_text=candidate_text,
        token_logprobs=token_logprobs
    )

    # 2. Responsibility scan on model output
    out_pii, out_policy = responsibility_detector.scan_all(candidate_text)

    # 3. Cost & spend anomaly detection
    spend_anomaly = cost_detector.record_and_check_spend_anomaly(estimated_cost)
    db.record_spend(request_id=request_id, cost_usd=estimated_cost, tokens_used=tokens_used)

    # Aggregate Findings
    findings = DetectionFindings(
        performance_score=perf_score,
        self_rated_confidence=self_rated_conf,
        is_duplicate=False,
        spend_anomaly=spend_anomaly,
        pii_found=out_pii,
        policy_hits=out_policy
    )

    # 4. Confidence State Machine
    confidence = confidence_sm.evaluate(findings)

    # 5. Deterministic Decision Engine
    decision = decision_engine.decide(confidence, findings)

    # Apply decision action to final text
    final_content = candidate_text
    if decision.action == "BLOCK":
        final_content = f"[BLOCKED BY POLICY]: {', '.join(decision.reasons)}"
    elif decision.action == "EDIT":
        # Deterministically redact PII
        if findings.pii_found:
            final_content, _ = responsibility_detector.redact_pii(final_content)
        if decision.warning_banner:
            final_content = f"{decision.warning_banner}\n\n{final_content}"
    elif decision.action == "ESCALATE":
        # Day 6: Record in review_queue table for human review
        if decision.review_id:
            db.create_review_item(
                review_id=decision.review_id,
                request_id=request_id,
                raw_prompt=raw_prompt,
                candidate_answer=candidate_text,
                findings=findings.model_dump(),
                confidence_state=confidence.state,
                reasons=decision.reasons
            )
        # In synchronous live-chat mode, safely downgrade with warning banner
        if decision.warning_banner:
            final_content = f"{decision.warning_banner}\n\n{candidate_text}"

    # Cache successful clean response (Never cache errors or mock fallbacks)
    if (
        decision.action in ["ALLOW", "EDIT"]
        and not llm_output.get("error")
        and llm_output.get("provider") != "mock"
        and not final_content.startswith("[FACTS]:")
    ):
        prompt_hash = cost_detector.normalize_for_hash(raw_prompt)
        db.save_dedup_cache(prompt_hash, raw_prompt, final_content)

    latency_ms = (time.perf_counter() - start_time) * 1000.0

    # Persist Audit Log
    db.save_audit_log({
        "request_id": request_id,
        "user_id": request.user_id,
        "raw_prompt": raw_prompt,
        "normalized_intake": intake.model_dump(),
        "truth_prompt_version": envelope.version,
        "model_tier": tier,
        "model_name": model_name,
        "findings": findings.model_dump(),
        "confidence_state": confidence.state,
        "decision_action": decision.action,
        "decision_reasons": decision.reasons,
        "tokens_used": tokens_used,
        "estimated_cost_usd": estimated_cost,
        "latency_ms": latency_ms,
        "cached": False
    })

    return ChatResponse(
        request_id=request_id,
        content=final_content,
        decision=decision,
        confidence=confidence,
        findings=findings,
        intake=intake,
        tier=tier,
        model_used=model_name,
        cached=False,
        tokens_used=tokens_used,
        estimated_cost_usd=round(estimated_cost, 6),
        latency_ms=round(latency_ms, 2),
        final_system_prompt=system_prompt,
        final_user_prompt=raw_prompt
    )


# --- REVIEW QUEUE ENDPOINTS (Day 6) ---

@app.get("/v1/reviews")
async def get_review_queue(status: Optional[str] = None):
    """Retrieve human review queue items (all or filtered by status)."""
    items = db.get_review_queue(status=status)
    return {"reviews": items, "count": len(items)}


@app.post("/v1/review/{review_id}")
async def resolve_review(review_id: str, resolution: ReviewResolution):
    """Resolve a review queue item with approve, reject, or edit."""
    success = db.resolve_review_item(
        review_id=review_id,
        action=resolution.action,
        reviewer_note=resolution.note or ""
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"Review item {review_id} not found")
    return {
        "status": "success",
        "review_id": review_id,
        "resolution": resolution.action,
        "note": resolution.note
    }
