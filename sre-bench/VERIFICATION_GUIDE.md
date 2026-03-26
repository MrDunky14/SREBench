# SREBench Pre-Push Verification Guide

This guide walks you through verifying SREBench is ready for git push and submission.

---

## Quick Start (5 minutes)

### Option 1: Full Automated Verification (Recommended)

```bash
cd sre-bench
chmod +x verify_all.sh
./verify_all.sh
```

This runs all 10 verification steps automatically:
1. ✓ Checks dependencies
2. ✓ Verifies project structure
3. ✓ Builds Docker image
4. ✓ Starts the server
5. ✓ Tests all 7 API endpoints
6. ✓ Runs solution caching tests
7. ✓ Runs comprehensive endpoint tests
8. ✓ Verifies all 3 tasks complete
9. ✓ Checks reproducibility
10. ✓ Shows summary

**Expected output:** "✓ ALL VERIFICATION TESTS PASSED"

---

## Manual Verification (Step-by-Step)

If you prefer to run tests manually or the script doesn't work, follow these steps:

### Step 1: Install Dependencies

```bash
cd sre-bench
pip install -r requirements.txt
```

Expected output:
```
Successfully installed fastapi==0.104.1 uvicorn==0.24.0 pydantic==2.5.0 ...
```

### Step 2: Verify Project Structure

Check that all required files exist:

```bash
ls -la src/
ls -la graders/
ls -la *.py *.txt *.md *.yaml Dockerfile
```

Expected files:
- ✓ `src/models.py`
- ✓ `src/infrastructure.py`
- ✓ `src/environment.py`
- ✓ `src/server.py`
- ✓ `graders/easy.py`
- ✓ `graders/medium.py`
- ✓ `graders/hard.py`
- ✓ `baseline.py`
- ✓ `requirements.txt`
- ✓ `Dockerfile`
- ✓ `README.md`
- ✓ `openenv.yaml`

### Step 3: Build Docker Image

```bash
docker build -t sre-bench:latest .
```

Expected output:
```
Successfully tagged sre-bench:latest
```

Check image size:
```bash
docker images sre-bench:latest
```

Expected: ~629MB

### Step 4: Start the Server

```bash
# Kill any existing server on port 8000
lsof -ti:8000 | xargs kill -9 || true

# Start server
cd sre-bench
uvicorn src.server:app --host 127.0.0.1 --port 8000 &
sleep 3
```

Expected output:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

### Step 5: Test All Endpoints

#### 5.1 Health Check

```bash
curl -s http://localhost:8000/ | jq .
```

Expected:
```json
{
  "status": "ok",
  "message": "SREBench environment is running"
}
```

#### 5.2 Get Tasks

```bash
curl -s http://localhost:8000/tasks | jq '.tasks[].id'
```

Expected:
```
"easy_restart"
"medium_cascade"
"hard_intermittent"
```

#### 5.3 Reset Episode

```bash
curl -s -X POST http://localhost:8000/reset \
  -H "Content-Type: application/json" \
  -d '{"task_id":"easy_restart"}' | jq '.system_dashboard[0].name'
```

Expected:
```
"api-gateway"
```

#### 5.4 Get State

```bash
curl -s http://localhost:8000/state | jq '.episode_id'
```

Expected:
```
"a1b2c3d4"  (some hex string)
```

#### 5.5 Execute Action

```bash
curl -s -X POST http://localhost:8000/step \
  -H "Content-Type: application/json" \
  -d '{
    "action_type": "investigate",
    "command": "check_logs",
    "target": "payment-service",
    "params": {"severity": "ERROR", "last_n": 10}
  }' | jq '.reward.value'
```

Expected:
```
0.03  (some positive reward)
```

#### 5.6 Get Grader Score

```bash
curl -s http://localhost:8000/grader | jq '.score'
```

Expected:
```
0.15  (score between 0.0 and 1.0)
```

#### 5.7 Run Baseline

```bash
curl -s -X POST http://localhost:8000/baseline \
  -H "Content-Type: application/json" \
  -d '{"task_id":"easy_restart"}' | jq '{steps, score}'
```

Expected:
```json
{
  "steps": 1,
  "score": 1.0
}
```

### Step 6: Test Solution Caching

```bash
cd sre-bench
python test_solution_caching.py
```

Expected output:
```
✓ SOLUTION CACHING CONFIRMED:
  - Optimal solution cached after run 1
  - Run 2 produced identical results
```

This confirms:
- ✓ First run caches optimal solution
- ✓ Second run produces identical score and steps
- ✓ Natural variance will emerge from suboptimal strategies

### Step 7: Run Comprehensive Tests

```bash
python test_comprehensive.py
```

Expected output:
```
✓ All 10 endpoint tests passed
✓ Solution caching verified
✓ All 3 incident scenarios working
✓ Deterministic grading confirmed
```

### Step 8: Verify All Tasks

Run each task individually to verify they complete:

```bash
# Terminal 1: Keep server running
# Terminal 2: Test each task

for task in easy_restart medium_cascade hard_intermittent; do
  echo "Testing $task..."
  curl -s -X POST http://localhost:8000/reset \
    -H "Content-Type: application/json" \
    -d "{\"task_id\":\"$task\"}" > /dev/null
  
  sleep 1
  
  curl -s -X POST http://localhost:8000/baseline \
    -H "Content-Type: application/json" \
    -d "{\"task_id\":\"$task\"}" | jq '{task_id, steps, score}'
done
```

Expected output:
```json
{
  "task_id": "easy_restart",
  "steps": 1,
  "score": 1.0
}
{
  "task_id": "medium_cascade",
  "steps": 4,
  "score": 0.95
}
{
  "task_id": "hard_intermittent",
  "steps": 3,
  "score": 0.95
}
```

### Step 9: Verify Reproducibility

Run the same task twice and confirm identical results:

```bash
# Run 1
curl -s -X POST http://localhost:8000/reset \
  -H "Content-Type: application/json" \
  -d '{"task_id":"easy_restart"}' > /dev/null

curl -s -X POST http://localhost:8000/baseline \
  -H "Content-Type: application/json" \
  -d '{"task_id":"easy_restart"}' | jq '{steps, score}'

sleep 1

# Run 2
curl -s -X POST http://localhost:8000/reset \
  -H "Content-Type: application/json" \
  -d '{"task_id":"easy_restart"}' > /dev/null

curl -s -X POST http://localhost:8000/baseline \
  -H "Content-Type: application/json" \
  -d '{"task_id":"easy_restart"}' | jq '{steps, score}'
```

Expected: Both runs return identical `steps` and `score`

---

## Verification Checklist

Once all tests pass, you can be confident about pushing to git:

- [ ] All dependencies installed
- [ ] Project structure complete (12 key files)
- [ ] Docker image builds successfully (~629MB)
- [ ] Server starts without errors
- [ ] All 7 endpoints respond correctly:
  - [ ] GET / (health)
  - [ ] GET /tasks (list)
  - [ ] POST /reset (initialize)
  - [ ] GET /state (fetch state)
  - [ ] POST /step (action)
  - [ ] GET /grader (score)
  - [ ] POST /baseline (run)
- [ ] Solution caching verified (identical runs)
- [ ] All 3 tasks complete successfully:
  - [ ] easy_restart (1 step, 1.0 score)
  - [ ] medium_cascade (4 steps, 0.95 score)
  - [ ] hard_intermittent (3 steps, 0.95 score)
- [ ] Reproducibility confirmed
- [ ] All comprehensive tests pass

---

## Troubleshooting

### Server won't start

```bash
# Check if port 8000 is in use
lsof -i :8000

# Kill any existing process
kill -9 <PID>

# Try starting again
uvicorn src.server:app --host 127.0.0.1 --port 8000
```

### Docker build fails

```bash
# Check for syntax errors
docker build -t sre-bench . --progress=plain

# Check requirements.txt
pip list | grep -E "fastapi|uvicorn|pydantic"

# Rebuild from scratch
docker system prune -a
docker build -t sre-bench .
```

### Tests fail

```bash
# Check server is running
curl -s http://localhost:8000/ | jq .

# Check server logs
tail -50 /tmp/server.log

# Run tests with verbose output
python -u test_comprehensive.py
```

### Endpoint returns error

```bash
# Check the exact error response
curl -s -X POST http://localhost:8000/reset \
  -H "Content-Type: application/json" \
  -d '{"task_id":"easy_restart"}' | jq .

# Check server logs for stack trace
tail -100 /tmp/server.log
```

---

## What Gets Validated

### Code Quality
- ✓ All imports work
- ✓ No syntax errors
- ✓ Pydantic models validate
- ✓ Infrastructure graph builds
- ✓ Graders calculate scores

### Functionality
- ✓ Episodes can be reset
- ✓ Actions execute properly
- ✓ Rewards calculate correctly
- ✓ Incidents resolve
- ✓ Graders score fairly

### Reproducibility
- ✓ Same episode_id → same incident
- ✓ Same actions → same outcome
- ✓ Baseline replays identically
- ✓ Solution caching works
- ✓ Scores are deterministic

### Completeness
- ✓ All 3 tasks solvable
- ✓ All 7 endpoints working
- ✓ All dependencies specified
- ✓ Docker containerizes
- ✓ Documentation complete

---

## After Verification Passes

Once verification is complete:

```bash
# Stop the server
pkill -f "uvicorn src.server"

# Check git status
cd /workspaces/SREBench
git status

# Review changes
git diff --stat

# Stage all changes
git add -A

# Commit
git commit -m "SREBench: Complete implementation with solution caching

- 6-service microservice simulator with realistic dependencies
- 3 incident scenarios (easy/medium/hard) with deterministic seeding
- Solution caching mechanism (reproducible baseline + natural variance)
- Dense reward shapingwith 5 components
- Full OpenEnv spec compliance
- 7 API endpoints with comprehensive testing
- Docker containerization
- Complete documentation"

# Push to remote
git push origin main
```

---

## Success Criteria

✅ **You can safely push when:**

```
✓ Authentication passes (no failures)
✓ All 7 endpoints respond correctly
✓ All 3 tasks complete with expected scores
✓ Solution caching works (reproducible runs)
✓ Docker builds successfully
✓ Comprehensive tests pass (10/10)
✓ No error messages in server logs
```

---

## Expected Results Summary

| Task | Steps | Score | Reproducible? |
|------|-------|-------|--------------|
| easy_restart | 1 | 1.0 | ✓ Yes |
| medium_cascade | 4 | 0.95 | ✓ Yes |
| hard_intermittent | 3 | 0.95 | ✓ Yes |

**Reproducibility:** Run the same task twice → get identical steps and scores ✓

**Variance:** Different strategies → different step counts → different scores ✓

---

## Ready to Push!

Once you see the green checkmarks above, you can confidently push to git. The submission is complete and ready for evaluation.

Good luck! 🚀
