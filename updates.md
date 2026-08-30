# ControlPlane Wrapper — Project Updates & Changelog (`updates.md`)

This document tracks all design decisions, architectural evolutions, implemented milestones, and updates across the ControlPlane project.

---

## 1. Project Overview & Evolution

The ControlPlane wrapper was conceived to solve two fundamental problems in production LLM deployments:
1. **Wrong-but-Confident Responses**: Models output hallucinations with high linguistic confidence without signaling uncertainty.
2. **Unnecessary Token Spend & Duplication**: Teams burn money routing simple queries to expensive frontier models or running identical prompts repeatedly.

### Core Architectural Decisions & Updates

| Update / Decision | Previous Concept | Current Architecture | Rationale |
|---|---|---|---|
| **Pipeline Architecture** | Complex 11-stage pipeline | **2-Stage Lightweight Wrapper** (Stage 1: Prevention, Stage 2: Detection) | Achieves 90%+ of risk reduction with zero orchestration overhead and fast time-to-market. |
| **Intake Mechanism** | Heavy iterative multi-turn dialogue | **4-Question Structured Intake** (Task, Context, Constraints, Expected Output) with dual-mode resolution (heuristic inference or single clarifying question, never both) | Prevents token waste from re-prompting while bounding round-trips. |
| **Confidence Assessment** | 5-state complex machine (VERIFIED / HIGH / QUALIFIED / LOW / UNVERIFIABLE) | **3-State Evidence-Based Machine** (HIGH / QUALIFIED / LOW) | Clear operational semantics, easier to write comprehensive test suites and deterministic policy matrices. |
| **Policy Enforcement** | Second LLM judge / evaluator | **Deterministic `policy.yaml` Lookup** | Rule-matching provides 100% reproducible, explainable, and zero-token-overhead decisions. |
| **Storage & Caching** | Distributed Redis + PostgreSQL + Vector DB | **Self-contained SQLite storage** | Zero infrastructure ops; stores audit logs, dedup cache, and spend counters in a single file. |
| **PII & Safety** | Heavy ML neural classifiers | **Regex / Keyword pattern scanner with swappable interface** | Sub-millisecond execution; easily upgradable to Presidio/Guardrails later without changing interface. |
| **Model Routing** | LLM-based query classifier | **Rule-based heuristic router** (token count, task type, complexity triggers) | Zero tokens wasted on deciding which model to invoke. |

---

## 2. Implemented Features & Updates Log

### Version 0.1.0 — Foundation & Scaffolding
- **Established Project Architecture**:
  - Defined decoupled directory layout (`app/`, `app/detectors/`, `tests/`).
  - Created standardized requirements in `requirements.txt`.
- **Created Core Data Contracts (`app/core_types.py`)**:
  - `IntakeResult`: Task, Context, Constraints, Expected Output, Source.
  - `TruthPromptEnvelope`: Versioned prompt wrapper with fact separation instructions.
  - `DetectionFindings`: Performance logprob/entropy, self-rated confidence, dedup hit, spend anomaly, PII hits, policy hits.
  - `ConfidenceResult`: 3-state confidence representation with reasoning breakdown.
  - `Decision`: ALLOW, FLAG, BLOCK actions with customizable warning banners.
  - `ChatRequest` & `ChatResponse`: Full end-to-end API payloads.
- **Implemented Prevention Stage Modules**:
  - `app/truth_prompt.py`: Template engine injecting fact/assumption segregation and bias-neutral instructions.
  - `app/intake.py`: 4-field normalization engine using regex and keyword heuristics.
  - `app/router.py`: Heuristic tiered router directing requests to `cheap` or `capable` tiers.
- **Implemented Detection Stage Modules**:
  - `app/detectors/performance.py`: Token logprob / sequence entropy evaluator with fallback self-rating parser.
  - `app/detectors/cost.py`: SQLite-backed exact/semantic dedup cache and rolling spend rate anomaly monitor.
  - `app/detectors/responsibility.py`: Dual-pass input/output PII (email, phone, SSN, API key) and policy ruleset validator.
- **Implemented Decision & Orchestration Layer**:
  - `app/confidence.py`: State synthesizer mapping combined detector findings to `HIGH`, `QUALIFIED`, or `LOW`.
  - `app/decision.py`: Policy lookup engine applying rules from `app/policy.yaml`.
  - `app/providers.py`: Extensible provider client with mock and live provider support.
  - `app/db.py`: SQLite persistence layer for audit logs, spend logs, and dedup records.
  - `app/main.py`: FastAPI server with `/v1/chat`, `/health`, and `/audit` endpoints.
- **Created Full Documentation Suite**:
  - `context.md`: The philosophical and business rationale ("Why").
  - `plan.md`: The vertical slice 5-day roadmap ("What to build").
  - `pipeline.md`: The comprehensive technical dataflow specification ("How it works").
  - `updates.md`: The evolutionary history and changelog ("What we have done").
  - `current_state.md`: The current readiness assessment and next actions ("Where we stand").

---

## 3. TruthPrompt Template Versioning

### `truth_prompt_v1` (Current)
Injected system prompt enforcing structured reasoning:
```markdown
You are an evidence-driven AI assistant operating under the ControlPlane wrapper.

For every request:
1. Decompose the request into core sub-problems.
2. Explicitly separate what is VERIFIED FACT from what is INFERENCE or ASSUMPTION.
3. Solve the task adhering strictly to user constraints.
4. Verify your solution against the verified facts.
5. Provide an estimated confidence score (0.0 to 1.0) and specify any remaining uncertainties.
6. Adhere to bias-neutral, inclusive framing without unsupported demographic assumptions.
```

---

## 4. Upcoming Roadmap & Iteration Tracker

- [x] Scaffolding, Data Contracts, and Pipeline Design
- [x] Standalone Unit Test Suites (`tests/`) — 19 Tests Passing
- [x] Integration Testing & Live Provider Verification (`test_pipeline.py`)
- [x] Automated 5-Step Smoke Test Suite (`smoke_test.py`)
- [x] Interactive Terminal CLI (`cli.py`) with Audit Inspection
- [x] Semantic Deduplication via n-gram cosine vector similarity
- [x] Multi-Provider Dispatch (OpenAI, Claude, Gemini, Mock)
- [x] Glassmorphic Interactive Web Dashboard (`app/static/`)
- [ ] Multi-tenant quota management
