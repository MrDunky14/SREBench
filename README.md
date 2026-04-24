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

## 🏆 Hackathon Submission Links (Mandatory)

| Resource | Link |
|---|---|
| **🚀 Hugging Face Space** | [https://huggingface.co/spaces/CreatorNeuron/sre-bench](https://huggingface.co/spaces/CreatorNeuron/sre-bench) |
| **📓 Colab Notebook** | [https://colab.research.google.com/drive/[YOUR_COLAB_ID_HERE]](https://colab.research.google.com/drive/[YOUR_COLAB_ID_HERE]) *(Note: Used Kaggle T4 for 30h quota)* |
| **💻 Code Repository** | [https://github.com/MrDunky14/SREBench](https://github.com/MrDunky14/SREBench) |
| **📝 HF Blog Post** | [SREBench: Teaching LLMs to Fix Production Incidents](BLOG_POST.md) |

---

## 🎯 Quick Links

| | Link |
|---|---|
| **🌐 Live Space** | https://huggingface.co/spaces/CreatorNeuron/sre-bench |
| **📖 Full Docs** | [sre-bench/README.md](sre-bench/README.md) |
| **⚙️ API Docs** | https://creatorneuron-sre-bench.hf.space/docs |
| **💻 GitHub Repo** | https://github.com/MrDunky14/SREBench |
| **📜 Blog Post** | [SREBench: Teaching LLMs to Fix Production Incidents](BLOG_POST.md) |
| **🧪 Latest Audit** | [Audit Report (2026-04-24)](AUDIT_REPORT_2026-04-24.md) |
| **📋 Audit JSON** | [audit_results.json](audit_results.json) |

---

## 📰 Recent News

### 🚀 **GRPO Training with TRL & Unsloth** (April 2026)

We've released `train_grpo.py`—a complete training pipeline for fine-tuning LLMs on SREBench using:

- **GRPO** (Generative Reward-Optimized) training from [TRL](https://huggingface.co/docs/trl/)
- **Unsloth** for 4-bit quantization and efficient LoRA fine-tuning
- **Curriculum learning** (easy → medium → hard incidents)

**Quick Start:**
```bash
pip install -r requirements.txt
cd sre-bench
python train_grpo.py --steps 50 --model "unsloth/Llama-3.2-1B-Instruct"
```

**Results**: Baseline collection and training in progress. Run `--dry-run` for baseline plots.

📖 **Full details**: [Read the blog post →](BLOG_POST.md)

---

## 🏗️ What You Get

**5 production-grade incident tasks with escalating difficulty:**

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

### Task 4: Network Partition Crisis 🌐 (Expert)
- **Scenario**: Replica synchronization breaks due to a network partition between primary and replica databases
- **Difficulty**: Requires reading replication lag signals and choosing failover at the right time
- **Expected**: Higher-step expert diagnosis and remediation

### Task 5: Database Sync Failure 🧬 (Expert)
- **Scenario**: Replica sync failure caused by WAL synchronization issues
- **Difficulty**: Requires tracing replication health and recovering the database path safely
- **Expected**: Higher-step expert diagnosis and remediation

---

## 🌟 Key Features

✅ **OpenEnv Compliant** — Follows official OpenEnv specification  
✅ **Anti-Exploit Hardened** — Ground truth hidden, shotgun restarts penalized, rollback neutered  
✅ **Stochastic Metrics** — No two episodes are identical (Gaussian jitter on all fault values)  
✅ **Dense Reward Function** — 5-component reward: investigation, diagnosis, remediation, safety penalty, resolution bonus  
✅ **Production Realism** — Real failure modes: OOM kills, connection exhaustion, cache fragmentation  
✅ **Scalable Difficulty** — 5 tasks from trivial to expert-level  
✅ **Investigation-First Design** — Agents must investigate ≥2 services before diagnosis is credited  

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

## 📡 API Endpoints (11 total)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/` | Health check |
| GET | `/tasks` | List 5 available incident tasks |
| POST | `/reset` | Initialize episode with incident injection |
| GET | `/state` | Current system state (ground truth withheld) |
| POST | `/step` | Execute an agent action (investigate, diagnose, remediate) |
| GET | `/grader` | Get final episode score |
| GET | `/leaderboard` | View task leaderboards |
| POST | `/baseline` | Run baseline strategy end-to-end |
| GET | `/dashboard.html` | Interactive dashboard |
| GET | `/index.html` | Static homepage |
| GET | `/docs-api` | Machine-readable API summary |

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
- ✅ All 11 API endpoints working
- ✅ All 5 incident tasks completable (scores 0.79–0.95)
- ✅ 9/9 anti-exploit tests passing
- ✅ Stochastic metrics confirmed (no deterministic values)
- ✅ Docker builds successfully
- ✅ GRPO training script tested (dry-run + GPU modes)

**Repository**: Clean, documented, no secrets exposed

**Status**: Hardened and ready for Grand Finale

---

## 📚 Full Documentation

For architectural details, reward function specifics, observation/action space schemas, and advanced grading logic, see [sre-bench/README.md](sre-bench/README.md).

---

## 🎓 Hackathon Submission

**Live Environment**: https://huggingface.co/spaces/CreatorNeuron/sre-bench  
**GitHub Repository**: https://github.com/MrDunky14/SREBench  
**Grand Finale**: April 25-26, 2026 (Bangalore)