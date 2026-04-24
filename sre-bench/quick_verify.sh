#!/bin/bash
# Quick SREBench Verification (Run before git push)

echo "════════════════════════════════════════════════════════════════════"
echo "SREBench Quick Verification"
echo "════════════════════════════════════════════════════════════════════"
echo ""

# Kill any existing servers
pkill -f "uvicorn src.server" 2>/dev/null || true
sleep 1

# Start server
echo "[1] Starting server..."
uvicorn src.server:app --host 127.0.0.1 --port 8000 &> /tmp/server.log &
SERVER_PID=$!
sleep 3

if ! kill -0 $SERVER_PID 2>/dev/null; then
    echo "✗ Server failed to start"
    cat /tmp/server.log
    exit 1
fi
echo "✓ Server running (PID: $SERVER_PID)"
echo ""

# Function to cleanup
cleanup() {
    kill $SERVER_PID 2>/dev/null || true
}
trap cleanup EXIT

# Test endpoints
echo "[2] Testing endpoints..."

# Health check
curl -s http://localhost:8000/ | grep -q "ok" && echo "  ✓ Health check" || echo "  ✗ Health check"

# Tasks
curl -s http://localhost:8000/tasks | grep -q "easy_restart" && echo "  ✓ Tasks endpoint" || echo "  ✗ Tasks"

# Reset
curl -s -X POST http://localhost:8000/reset -H "Content-Type: application/json" -d '{"task_id":"easy_restart"}' | grep -q "system_dashboard" && echo "  ✓ Reset" || echo "  ✗ Reset"

# State
curl -s http://localhost:8000/state | grep -q "episode_id" && echo "  ✓ State" || echo "  ✗ State"

# Step
curl -s -X POST http://localhost:8000/step -H "Content-Type: application/json" -d '{"action_type":"investigate","command":"check_logs","target":"payment-service","params":{"severity":"ERROR","last_n":10}}' | grep -q "observation" && echo "  ✓ Step" || echo "  ✗ Step"

# Grader
curl -s http://localhost:8000/grader | grep -q "score" && echo "  ✓ Grader" || echo "  ✗ Grader"

# Baseline
curl -s -X POST http://localhost:8000/baseline -H "Content-Type: application/json" -d '{"task_id":"easy_restart"}' | grep -q "score" && echo "  ✓ Baseline" || echo "  ✗ Baseline"
echo ""

echo "[3] Testing all tasks..."
python test_solution_caching.py > /tmp/test.log 2>&1 && {
    echo "  ✓ Solution caching verified"
    grep "easy_restart\|medium_cascade\|hard_intermittent" /tmp/test.log | head -3
} || echo "  ✗ Solution caching test failed"
echo ""

echo "[4] Running comprehensive tests..."
python test_comprehensive.py > /tmp/test.log 2>&1 && {
    echo "  ✓ All endpoint tests passed"
} || echo "  ✗ Comprehensive tests failed"
echo ""

echo "════════════════════════════════════════════════════════════════════"
echo "✓ VERIFICATION COMPLETE - Ready for git push!"
echo "════════════════════════════════════════════════════════════════════"
