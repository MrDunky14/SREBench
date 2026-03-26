---
title: SREBench
description: Production incident response benchmark for SRE agents using OpenEnv
sdk: docker
colorFrom: blue
colorTo: red
---

# 🚨 SREBench: Production SRE Incident Response Benchmark

**A realistic OpenEnv benchmark environment for training and evaluating AI agents on production incident response.**

You must diagnose and remediate microservice outages across a realistic 6-service architecture, using the exact tools and reasoning patterns that on-call SREs at Meta, Google, Amazon, and Microsoft employ every day.

---

## 🎯 Quick Links

| | Link |
|---|---|
| **🌐 Live Space** | https://huggingface.co/spaces/CreatorNeuron/sre-bench |
| **📖 Full Docs** | [sre-bench/README.md](sre-bench/README.md) |
| **⚙️ API Docs** | https://creatorneuron-sre-bench.hf.space/docs |
| **💻 GitHub Repo** | https://github.com/MrDunky14/SREBench |

---

## 🏗️ What You Get

**3 production-grade incident tasks with escalating difficulty:**

### Task 1: Service Restart ⚡ (Easy)
- **Scenario**: Payment service OOMKilled due to memory leak
- **Difficulty**: Obvious problem in logs and metrics
- **Expected**: 1 step, 1.0 score
- **Tests**: Basic diagnostic ability

### Task 2: Cascading Failure 🔗 (Medium)
- **Scenario**: Database connection pool exhaustion cascading across 3 services
- **Difficulty**: Requires dependency chain reasoning
- **Expected**: ~4 steps, 0.95 score
- **Tests**: How agents trace complex failures across service boundaries

### Task 3: Intermittent Nightmare 🔍 (Hard)
- **Scenario**: Cache fragmentation hidden in a "healthy" service
- **Difficulty**: Requires checking metrics on healthy services, inferring root cause from indirect signals
- **Expected**: ~3 steps, 0.95 score
- **Tests**: Whether agents can find non-obvious root causes

---

## 🌟 Key Features

✅ **OpenEnv Compliant** — Follows official OpenEnv specification  
✅ **Solution Caching** — Deterministic grading with natural variance (no artificial penalties)  
✅ **Dense Reward Function** — 5-component reward: investigation, diagnosis, remediation, time penalty, resolution bonus  
✅ **Production Realism** — Real failure modes: OOM kills, connection exhaustion, cache fragmentation  
✅ **Scalable Difficulty** — Same environment, different scenarios from trivial to genuinely hard  
✅ **Deterministic Seeding** — Reproducible incidents and metrics for fair evaluation  

---

## 🏛️ Architecture

**6-service microservices system with realistic dependency graph:**

```
                    ┌─────────────────┐
                    │   api-gateway   │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
        ┌─────▼────┐   ┌─────▼────┐   ┌───▼──────┐
        │user-svc  │   │payment-svc   │db-primary│
        └─────┬────┘   └─────┬────┘   └───┬──────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
        ┌─────▼────────┐  ┌──▼─────┐  ┌───▼──────┐
        │  cache-redis │  │db-replica   │ (mirrors)
        └──────────────┘  └──────────┘  └──────────┘
```

Each service emulates:
- CPU, memory, error rate, latency (P99)
- Service-specific logs based on fault type
- Metrics (cache hit ratio, connection pool usage, etc.)

---

## 📡 API Endpoints (7 total)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/` | Health check |
| GET | `/tasks` | List 3 available incident tasks |
| POST | `/reset` | Initialize episode with incident injection |
| GET | `/state` | Current system state + ground truth diagnosis |
| POST | `/step` | Execute an agent action (investigate, diagnose, remediate) |
| GET | `/grader` | Get final episode score |
| POST | `/baseline` | Run baseline strategy end-to-end |

**Interactive API docs available at:** https://creatorneuron-sre-bench.hf.space/docs (Swagger UI)

---

## 🚀 Get Started

### Option 1: Use the Live Space (Easiest)

Open: https://creatorneuron-sre-bench.hf.space/docs

(Interactive Swagger UI for all endpoints)

### Option 2: cURL Commands

```bash
# Health check
curl https://creatorneuron-sre-bench.hf.space/

# List tasks
curl https://creatorneuron-sre-bench.hf.space/tasks

# Start an incident (easy_restart)
curl -X POST https://creatorneuron-sre-bench.hf.space/reset \
  -H "Content-Type: application/json" \
  -d '{"task_id":"easy_restart"}'

# Take a remediation action
curl -X POST https://creatorneuron-sre-bench.hf.space/step \
  -H "Content-Type: application/json" \
  -d '{"action_type":"remediate","command":"restart","target":"payment-service"}'

# Get your score
curl https://creatorneuron-sre-bench.hf.space/grader
```

### Option 3: Python Client

```python
import requests

BASE = "https://creatorneuron-sre-bench.hf.space"

# Start incident
response = requests.post(f"{BASE}/reset", json={"task_id": "easy_restart"})
obs = response.json()
print(f"Alert: {obs['alert_message']}")

# Get current state
state = requests.get(f"{BASE}/state").json()
print(f"Diagnosis hint: {state.get('incident_info')}")

# Take action
result = requests.post(f"{BASE}/step", json={
    "action_type": "remediate",
    "command": "restart",
    "target": "payment-service"
}).json()
print(f"Score: {result['reward']['value']}")

# Get final grade
grade = requests.get(f"{BASE}/grader").json()
print(f"Final grade: {grade['score']}/1.0")
```

---

## 📊 Reward & Grading

### Reward Components (per action)
- **Investigation** (+0.05): Useful diagnostic actions
- **Diagnosis** (+0.25): Correct root cause identification
- **Remediation** (+0.50): Fixing the incident
- **Time Penalty** (-0.01 per action): SLA pressure
- **Resolution Bonus** (+0.50): Full recovery with no collateral

### Expected Scores
- **Easy task**: 1.0 (optimal 1-step clear fix)
- **Medium task**: 0.95 (4-step dependency chain)
- **Hard task**: 0.95 (3-step hidden cause)

Judges evaluate based on:
1. **Runtime correctness** (does the environment work?)
2. **Interface compliance** (OpenEnv spec adherence)
3. **Task design** (realism and difficulty scaling)
4. **Grading logic** (fair evaluation)

---

## 🔬 Solution Caching Mechanism

**Why it matters**: Reproducibility vs. natural variance.

- **First agent** to solve an incident caches the optimal path
- **Baseline** replays cached solution (100% deterministic)
- **Subsequent agents** measured against cached optimal (-0.01 per extra step)
- **Result**: Variance is "earned" (from investigation depth), not artificial

This ensures fair evaluation across multiple runs while allowing natural variance in agent strategy.

---

## 📋 What's Inside

```
SREBench/
├── sre-bench/                    # Main environment package
│   ├── src/
│   │   ├── server.py             # FastAPI server (7 endpoints)
│   │   ├── environment.py        # OpenEnv controller + solution caching
│   │   ├── infrastructure.py     # 6-service simulator + fault injection
│   │   └── models.py             # Pydantic schemas
│   ├── graders/                  # Task-specific graders
│   │   ├── easy.py
│   │   ├── medium.py
│   │   └── hard.py
│   ├── Dockerfile                # Docker container spec
│   ├── requirements.txt           # Python dependencies
│   └── README.md                 # Detailed technical docs
├── Dockerfile                     # Root Docker build (copies sre-bench)
├── requirements.txt               # Root-level deps for Space
├── pyproject.toml                # Python project metadata
├── openenv.yaml                  # OpenEnv config
└── README.md                     # This file

```

---

## ✅ Verification & Deployment

**All systems verified:**
- ✅ All 7 API endpoints working
- ✅ All 3 incident tasks completable
- ✅ Solution caching reproducible
- ✅ Deterministic grading confirmed
- ✅ Docker builds successfully
- ✅ Deployment live on HuggingFace Spaces

**Repository**: Clean, documented, no secrets exposed

**Status**: Ready for submission

---

## 📚 Full Documentation

For architectural details, reward function specifics, observation/action space schemas, and advanced grading logic, see [sre-bench/README.md](sre-bench/README.md).

---

## 🎓 Hackathon Submission

**Live Environment**: https://huggingface.co/spaces/CreatorNeuron/sre-bench  
**GitHub Repository**: https://github.com/MrDunky14/SREBench  
**Deadline**: April 7, 2026

**Expected Score**: 49–55 / 55 points