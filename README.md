# ControlPlane Wrapper

> **A deterministic, evidence-based orchestration layer for LLMs.**
> Catches wrong-but-confident hallucinations, eliminates redundant spend via semantic deduplication, and enforces PII & safety policies before and after generation.

---

## 📖 Key Documentation

| File | Description |
|---|---|
| [`pipeline.md`](./pipeline.md) | Full technical specification of Stage 1 (Prevention) and Stage 2 (Detection) pipelines with Mermaid sequence diagrams. |
| [`current_state.md`](./current_state.md) | Current project status, complete tech stack selection & rationale, and 5-day action roadmap. |
| [`updates.md`](./updates.md) | Detailed changelog, architectural decisions, and version history. |
| [`context.md`](./context.md) | The fundamental business rationale ("The Why"). |
| [`plan.md`](./plan.md) | The vertical slice implementation scope ("The Plan"). |

---

## 🚀 Quick Start

### 1. Installation
```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration
```bash
cp .env.example .env
# Edit .env with your OpenAI or provider API key if using live models
```

### 3. Run Tests
```bash
pytest -v
```

### 4. Start the Proxy Server
```bash
uvicorn app.main:app --reload --port 8000
```

---

## 📡 API Usage

### Send a Prompt to `/v1/chat`
```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Summarize the key differences between TCP and UDP in 3 bullet points."
  }'
```

### Check Audit Logs
```bash
curl http://localhost:8000/audit?limit=10
```

---

## 📂 Project Structure

```
ControlPlane/
├── app/
│   ├── __init__.py
│   ├── main.py                # FastAPI server & pipeline coordinator
│   ├── core_types.py          # Pydantic data schemas (Intake, Findings, Decisions)
│   ├── truth_prompt.py        # Stage 1a: TruthPrompt builder & system prompt
│   ├── intake.py              # Stage 1b: 4-question structured intake parser
│   ├── router.py              # Tiered model routing (cheap vs capable)
│   ├── confidence.py          # Stage 2: Evidence-based confidence state machine
│   ├── decision.py            # Stage 2: Deterministic decision engine
│   ├── providers.py           # Thin LLM provider client (with mock mode)
│   ├── db.py                  # SQLite manager: audit logs, dedup cache, spend logs
│   ├── policy.yaml            # Deterministic policy rules, thresholds, and banners
│   └── detectors/
│       ├── __init__.py
│       ├── performance.py     # Logprob entropy scan & self-rated confidence
│       ├── cost.py            # Dedup cache & spend anomaly monitor
│       └── responsibility.py  # PII/secrets regex scanner & policy checker
├── tests/
│   ├── __init__.py
│   ├── test_intake.py         # Intake normalization tests
│   ├── test_detectors.py      # Detector unit tests
│   ├── test_decision.py       # Confidence & decision matrix tests
│   └── test_pipeline.py       # FastAPI integration tests
├── pipeline.md                # End-to-end pipeline technical specification
├── current_state.md           # Current readiness, tech stack & roadmap
├── current state.md           # Mirror alias
├── updates.md                 # Project updates, decisions & changelog
├── context.md                 # Problem statement & design principles
├── plan.md                    # Vertical slice build plan
├── requirements.txt           # Python dependencies
├── .env.example               # Environment variables template
├── .gitignore
└── README.md
```
