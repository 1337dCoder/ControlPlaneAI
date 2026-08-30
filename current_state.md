# ControlPlane Wrapper — Current State & Tech Stack (`current_state.md`)

This document outlines the current state of the ControlPlane project, the technology stack chosen, what has been completed, what is in progress, and the exact next steps to take.

---

## 1. Executive Summary

ControlPlane is an intelligent proxy wrapper designed to sit between client applications and downstream LLM APIs. Its mission is to **prevent hallucinations**, **eliminate redundant spend**, and **enforce data safety policies** through a deterministic, evidence-based pipeline.

### System Readiness Matrix

| Component | Status | Description |
|---|---|---|
| **Architecture & Design** | ✅ Complete | Two-stage pipeline (Prevention + Detection) fully specified in `context.md`, `plan.md`, `pipeline.md`, and `updates.md`. |
| **Folder Structure** | ✅ Complete | Decoupled modular structure established (`app/`, `app/detectors/`, `tests/`). |
| **Data Contracts** | ✅ Complete | Pydantic data schemas in `app/core_types.py`. |
| **Stage 1 (Prevention)** | ✅ Scaffolding Complete | `truth_prompt.py`, `intake.py`, `router.py`. |
| **Stage 2 (Detection)** | ✅ Scaffolding Complete | `detectors/performance.py`, `detectors/cost.py`, `detectors/responsibility.py`. |
| **Confidence & Decision** | ✅ Complete | Evidence-based confidence state machine & policy lookup engine in `app/confidence.py` and `app/decision.py`. |
| **Storage & Database** | ✅ Complete | SQLite schema for audit logs, spend records, and dedup cache in `app/db.py`. |
| **API Server & Dashboard** | ✅ Complete | FastAPI endpoints (`/v1/chat`, `/health`, `/audit`, `/dashboard`) + Web UI in `app/main.py` & `app/static/`. |
| **Test Suites** | ✅ Complete | Comprehensive unit and integration tests in `tests/` (19 passing tests). |
| **CLI & Smoke Tests** | ✅ Complete | Interactive terminal client (`cli.py`) and automated test runner (`smoke_test.py`). |

---

## 2. Technology Stack & Technical Rationale

| Layer | Selected Tech Stack | Technical Rationale & Tradeoffs |
|---|---|---|
| **Language** | **Python 3.11+** | Industry standard for LLM orchestration, native type hinting, asynchronous I/O (`asyncio`), and fastest integration with AI ecosystem. |
| **Web Framework** | **FastAPI + Uvicorn** | High performance async ASGI framework, automatic OpenAPI documentation, native Pydantic validation, and minimal boilerplate. |
| **Data Validation** | **Pydantic v2** | Ultra-fast Rust-backed schema validation, strict type enforcement, and seamless JSON serialization. |
| **Configuration** | **PyYAML (`policy.yaml`)** | Human-readable configuration for detection thresholds, banned patterns, model tiers, and decision matrices without needing code changes or server redeployments. |
| **Database & Persistence** | **SQLite (via stdlib `sqlite3`)** | Zero-ops embedded database; requires no external server setup; handles audit logging, dedup lookups, and rolling spend tracking with ACID guarantees. |
| **HTTP Client** | **HTTPX** | Async HTTP client for outbound LLM API requests with connection pooling and timeout management. |
| **Testing** | **pytest + pytest-asyncio** | Industry standard testing framework for async endpoint tests, detector unit tests, and parameterized regression suites. |

---

## 3. What Has Been Done

1. **Architecture Blueprinting**: Completed comprehensive architectural specifications across `context.md`, `plan.md`, and `pipeline.md`.
2. **Scaffolding Creation**: Established clean directory structure separating API routing, core types, prevention mechanisms, detectors, policy engines, and database access.
3. **Data Contracts Definition**: Formalized Pydantic models for `IntakeResult`, `TruthPromptEnvelope`, `DetectionFindings`, `ConfidenceResult`, `Decision`, `ChatRequest`, and `ChatResponse`.
4. **Deterministic Policy Setup**: Created `app/policy.yaml` with explicit thresholds, banned regex patterns, model tier assignments, and confidence-to-action mappings (`ALLOW`, `FLAG`, `BLOCK`).
5. **Detector Logic**:
   - `responsibility.py`: Dual-pass regex PII scanner and keyword policy filter.
   - `cost.py`: SQLite-backed exact dedup hash cache and rolling spend rate monitor.
   - `performance.py`: Logprob entropy calculator and TruthPrompt confidence parser.
6. **Confidence & Decision Engines**:
   - `confidence.py`: Synthesizes findings into `HIGH`, `QUALIFIED`, or `LOW`.
   - `decision.py`: Evaluates confidence and findings against `policy.yaml`.
7. **FastAPI Endpoints & Database**: Implemented `/v1/chat`, `/health`, and `/audit` endpoints in `app/main.py` backed by SQLite storage in `app/db.py`.
8. **Unit Tests**: Authored test suites in `tests/test_intake.py`, `tests/test_detectors.py`, and `tests/test_decision.py`.

---

## 4. What To Do Next (5-Day Action Plan)

```mermaid
gantt
    title ControlPlane 5-Day Implementation Roadmap
    dateFormat  YYYY-MM-DD
    section Stage 1
    Day 1: Skeleton & TruthPrompt Integration       :done, d1, 2026-08-30, 1d
    Day 2: Structured Intake Heuristics Refinement  :active, d2, 2026-08-31, 1d
    section Stage 2
    Day 3: Tiered Model Routing & Provider Client   :d3, 2026-09-01, 1d
    Day 4: Detection Calibration (Perf/Cost/Resp)   :d4, 2026-09-02, 1d
    section Finalization
    Day 5: End-to-End Decision Wireup & Audit Demo  :d5, 2026-09-03, 1d
```

### Actionable Next Steps:
1. **Configure Environment Variables**:
   - Copy `.env.example` to `.env` and set your preferred provider API keys (`OPENAI_API_KEY`, etc.).
2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Run Test Suites**:
   ```bash
   pytest
   ```
4. **Launch Local Server**:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
5. **Execute Smoke Tests**:
   - Test 1: Clean request (`curl -X POST http://localhost:8000/v1/chat -H "Content-Type: application/json" -d '{"prompt": "Explain binary search"}'`)
   - Test 2: Duplicate request (verify cache hit and 0 token cost).
   - Test 3: PII request with fake SSN/API key (verify `BLOCK` or redaction).
