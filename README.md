---
title: SREBench
description: Production incident response benchmark for SRE agents using OpenEnv
sdk: docker
colorFrom: blue
colorTo: red
---

# SREBench

A realistic OpenEnv benchmark environment for training and evaluating AI agents on real-world Site Reliability Engineer (SRE) incident response tasks.

## Quick Start

```bash
pip install openai pydantic requests fastapi uvicorn
python -c "from client import env; obs = env.reset('easy_restart'); print(obs)"
```

## Overview

SREBench simulates a production microservices system with 6 interdependent services. An agent must investigate system health dashboards, analyze logs and metrics, diagnose root causes across service dependencies, and execute remediation actions—all under SLA time pressure.

## The 3 Incident Tasks

1. **easy_restart** (OOMKilled Service)
   - Diagnose a payment-service that crashed from OOM
   - Fix: Single restart command
   - Expected: ~1 step, 1.0 score

2. **medium_cascade** (Cascading Failure)
   - Database connection pool exhaustion cascading to downstream services
   - Fix: Increase pool size and drain excess connections
   - Expected: ~4 steps, 0.95 score

3. **hard_intermittent** (Cache Fragmentation)
   - Subtle cache hit ratio degradation from hidden metric
   - Fix: Clear and reconfigure Redis cache
   - Expected: ~3 steps, 0.95 score

## Key Features

✅ **OpenEnv Compliant** - Follows OpenEnv specification
✅ **Solution Caching** - Deterministic reproducibility with natural variance  
✅ **Dense Rewards** - Rich feedback throughout episode
✅ **Production Realistic** - Real incident patterns from Meta, Amazon, Google
✅ **Scalable Difficulty** - Easy/Medium/Hard tasks with automatic grading

## API Endpoints

- `GET /` - Health check
- `GET /tasks` - List available incident tasks
- `POST /reset` - Initialize new episode
- `GET /state` - Current system state (with ground truth)
- `POST /step` - Execute an action
- `GET /grader` - Grade a completed episode
- `POST /baseline` - Run baseline strategy

## Documentation

See [sre-bench/README.md](sre-bench/README.md) for detailed information including:
- Architecture diagram
- 6-service infrastructure details
- Observation/Action/Reward space specifications
- Grading logic and reward functions
- Solution caching mechanism