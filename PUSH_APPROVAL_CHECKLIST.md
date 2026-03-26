# ✅ SREBench - Pre-Push Verification & Approval Checklist

## Quick Start (Recommended - 2 minutes)

### Run Complete Verification

```bash
cd /workspaces/SREBench/sre-bench
bash quick_verify.sh
```

**Expected Output:**
```
════════════════════════════════════════════════════════════════════
SREBench Quick Verification
════════════════════════════════════════════════════════════════════

[1] Starting server...
✓ Server running (PID: XXXXX)

[2] Testing endpoints...
  ✓ Health check
  ✓ Tasks endpoint
  ✓ Reset
  ✓ State
  ✓ Step
  ✓ Grader
  ✓ Baseline

[3] Testing all tasks...
  ✓ Solution caching verified
  Task: easy_restart
  Task: medium_cascade
  Task: hard_intermittent

[4] Running comprehensive tests...
  ✓ All endpoint tests passed

════════════════════════════════════════════════════════════════════
✓ VERIFICATION COMPLETE - Ready for git push!
════════════════════════════════════════════════════════════════════
```

**If you see all ✓ checks → Ready to push!**

---

## What Gets Tested

### [1] Server Startup
- ✓ Uvicorn starts cleanly
- ✓ No port conflicts
- ✓ Application loads successfully

### [2] All 7 API Endpoints
- ✓ `GET /` - Health check (returns "ok")
- ✓ `GET /tasks` - List 3 tasks (easy/medium/hard)
- ✓ `POST /reset` - Initialize episode with incident
- ✓ `GET /state` - Fetch full episode state
- ✓ `POST /step` - Execute action and get reward
- ✓ `GET /grader` - Score current episode (0.0-1.0)
- ✓ `POST /baseline` - Run baseline strategy

### [3] Solution Caching
- ✓ First run caches optimal solution
- ✓ Subsequent runs replay identically
- ✓ No artificial variance
- ✓ Natural variance emerges from investigation depth

### [4] All Tasks Work
- ✓ `easy_restart` completes successfully
- ✓ `medium_cascade` traces to root cause
- ✓ `hard_intermittent` finds hidden metric

---

## Manual Verification (if you prefer)

### Step 1: Start Server

```bash
cd /workspaces/SREBench/sre-bench
uvicorn src.server:app --host 127.0.0.1 --port 8000 &
sleep 3
```

Check server is running:
```bash
curl -s http://localhost:8000/ | jq .
# Should return: {"status": "ok", "message": "..."}
```

### Step 2: Test Each Endpoint

**Health check:**
```bash
curl -s http://localhost:8000/ | jq .status
# Output: "ok"
```

**List tasks:**
```bash
curl -s http://localhost:8000/tasks | jq '.tasks[].id'
# Output: "easy_restart", "medium_cascade", "hard_intermittent"
```

**Initialize episode:**
```bash
curl -s -X POST http://localhost:8000/reset \
  -H "Content-Type: application/json" \
  -d '{"task_id":"easy_restart"}' | jq '.alert_message' | head -c 50
# Output: "=== INCIDENT ALERT ===..."
```

**Get state:**
```bash
curl -s http://localhost:8000/state | jq '.episode_id'
# Output: "a1b2c3d4" (some ID)
```

**Execute action:**
```bash
curl -s -X POST http://localhost:8000/step \
  -H "Content-Type: application/json" \
  -d '{
    "action_type": "investigate",
    "command": "check_logs",
    "target": "payment-service",
    "params": {"severity": "ERROR", "last_n": 10}
  }' | jq '.reward.value'
# Output: 0.03 (some positive reward)
```

**Score episode:**
```bash
curl -s http://localhost:8000/grader | jq '.score'
# Output: 0.2 (or similar, between 0.0-1.0)
```

**Run baseline:**
```bash
curl -s -X POST http://localhost:8000/baseline \
  -H "Content-Type: application/json" \
  -d '{"task_id":"easy_restart"}' | jq '{steps, score}'
# Output: {"steps": 1, "score": 1.0}
```

### Step 3: Run Python Tests

```bash
cd /workspaces/SREBench/sre-bench

# Test solution caching
python test_solution_caching.py

# Expected: "✓ SOLUTION CACHING CONFIRMED" for all 3 tasks

# Test comprehensive endpoints
python test_comprehensive.py

# Expected: "✓ All 10 endpoint tests passed"
```

### Step 4: Stop Server

```bash
pkill -f "uvicorn src.server"
```

---

## Approval Checklist

Check off each item before pushing:

- [ ] **Server starts** - `uvicorn src.server:app --host 127.0.0.1 --port 8000` runs without errors
- [ ] **Health check** - `curl http://localhost:8000/` returns `{"status": "ok"}`
- [ ] **Tasks endpoint** - Lists 3 tasks: easy_restart, medium_cascade, hard_intermittent
- [ ] **Reset works** - `POST /reset` returns observation with system_dashboard
- [ ] **State works** - `GET /state` returns episode_id and task_id
- [ ] **Step works** - `POST /step` executes action and returns observation + reward
- [ ] **Grader works** - `GET /grader` returns score between 0.0 and 1.0
- [ ] **Baseline works** - `POST /baseline` runs strategy and returns steps + score
- [ ] **Solution caching test passes** - `python test_solution_caching.py` shows ✓ for all tasks
- [ ] **Comprehensive test passes** - `python test_comprehensive.py` shows "✓ All 10 endpoint tests passed"

---

## Ready to Push?

Once all checks pass:

```bash
cd /workspaces/SREBench

# Check what will be committed
git status

# Stage changes
git add -A

# Commit with clear message
git commit -m "SREBench: Complete OpenEnv implementation with solution caching

Features:
- 6 microservices with dependency graph and cascading failures
- 3 incident scenarios (easy/medium/hard) with deterministic seeding
- Solution caching for reproducible baseline + natural variance
- Dense reward shaping with 5 components
- Full OpenEnv spec compliance (reset/step/state)
- 7 API endpoints (health, tasks, reset, step, state, grader, baseline)
- Docker containerization with 629MB image
- Comprehensive test suite (10+ tests)
- Complete documentation and guides"

# Push to remote
git push origin main
```

---

## Expected Final Results

| Component | Status | Details |
|-----------|--------|---------|
| Server startup | ✓ | Starts in <3 seconds |
| API health | ✓ | All 7 endpoints 200 OK |
| Task execution | ✓ | easy (1 step), medium (4 steps), hard (3 steps) |
| Grading | ✓ | Deterministic scores: easy (1.0), medium (0.95), hard (0.95) |
| Solution caching | ✓ | Identical scores across multiple runs |
| Docker | ✓ | Builds successfully (~629MB) |
| Tests | ✓ | 10 endpoint tests pass, caching verified |

---

## Troubleshooting

### Problem: "Port 8000 is already in use"

```bash
lsof -ti:8000 | xargs kill -9
sleep 1
# Try again
```

### Problem: "ModuleNotFoundError"

```bash
pip install -r requirements.txt
# Try again
```

### Problem: Test fails on specific endpoint

```bash
# Check server logs
tail -50 /tmp/server.log

# Try endpoint manually
curl -s http://localhost:8000/tasks | jq .

# Check error response
curl -v http://localhost:8000/tasks
```

### Problem: Solution caching test fails

```bash
# Ensure server is running AND tests use correct port
# Check test_solution_caching.py has: ENV_URL = "http://localhost:8000"

# Run test with verbose output
python -u test_solution_caching.py
```

---

## Final Sign-Off

You can safely push when you see:

```
════════════════════════════════════════════════════════════════════
✓ VERIFICATION COMPLETE - Ready for git push!
════════════════════════════════════════════════════════════════════
```

All checks ✓ → **Push with confidence!** 🚀

---

## Questions Before Push?

If anything fails or looks wrong:

1. Check server is running: `curl http://localhost:8000/`
2. Check logs: `tail -100 /tmp/server.log`
3. Run manual endpoint tests above
4. Re-read VERIFICATION_GUIDE.md for detailed explanations

Good luck! 🎉
