"""Full verification of LIVE HF Space deployment."""
import urllib.request, json, sys
sys.stdout.reconfigure(encoding="utf-8")
BASE = "https://creatorneuron-sre-bench.hf.space"

def post(path, data):
    req = urllib.request.Request(BASE + path, data=json.dumps(data).encode(),
                                headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())

def get(path):
    return json.loads(urllib.request.urlopen(BASE + path, timeout=30).read())

SERVICES = ["api-gateway", "user-service", "payment-service",
            "database-primary", "database-replica", "cache-redis"]
passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name} {detail}")
    else:
        failed += 1
        print(f"  FAIL: {name} {detail}")

# ── TEST 1: Ground truth hidden ──
print("=" * 60)
print("TEST 1: Ground Truth Leak via /state")
print("=" * 60)
post("/reset", {"task_id": "easy_restart"})
state = get("/state")
diag = state.get("incident_info", {}).get("ground_truth_diagnosis", "")
fix = state.get("incident_info", {}).get("ground_truth_fix", "")
check("Ground truth hidden", diag == "" and fix == "", f"diag='{diag}' fix='{fix}'")

# ── TEST 2: Shotgun restart penalized ──
print("\n" + "=" * 60)
print("TEST 2: Shotgun Restart Penalty")
print("=" * 60)
post("/reset", {"task_id": "easy_restart"})
for svc in SERVICES:
    r = post("/step", {"action_type": "remediate", "command": "restart", "target": svc, "params": {}})
    if r["done"]:
        break
grade = get("/grader")
check("Shotgun penalized", grade["score"] < 0.5, f"score={grade['score']:.3f}")

# ── TEST 3: Diagnosis skip penalized ──
print("\n" + "=" * 60)
print("TEST 3: Diagnosis Skip (no investigation)")
print("=" * 60)
post("/reset", {"task_id": "easy_restart"})
r = post("/step", {"action_type": "diagnose", "command": "submit_diagnosis",
                    "target": "payment-service", "params": {"root_cause": "oom_killed"}})
check("Premature diagnosis penalized", r["reward"]["value"] < 0.1, f"reward={r['reward']['value']:.3f}")

# ── TEST 4: Rollback not universal ──
print("\n" + "=" * 60)
print("TEST 4: Rollback Not Universal Fix")
print("=" * 60)
post("/reset", {"task_id": "easy_restart"})
post("/step", {"action_type": "investigate", "command": "check_logs", "target": "payment-service", "params": {}})
post("/step", {"action_type": "investigate", "command": "check_metrics", "target": "api-gateway", "params": {}})
r = post("/step", {"action_type": "remediate", "command": "rollback", "target": "payment-service", "params": {}})
grade = get("/grader")
check("Rollback not universal", grade["score"] < 0.5, f"score={grade['score']:.3f}")

# ── TEST 5: Stochastic metrics ──
print("\n" + "=" * 60)
print("TEST 5: Stochastic Metrics")
print("=" * 60)
cpus = set()
for i in range(3):
    obs = post("/reset", {"task_id": "easy_restart"})
    for svc in obs["system_dashboard"]:
        if svc["name"] == "payment-service":
            cpus.add(round(svc["cpu_percent"], 1))
check("Metrics stochastic", len(cpus) >= 2, f"unique={len(cpus)}/3 values={cpus}")

# ── TEST 6: Alert hides fault ──
print("\n" + "=" * 60)
print("TEST 6: Alert Hides Fault Type")
print("=" * 60)
obs = post("/reset", {"task_id": "easy_restart"})
alert = obs.get("alert_message", "")
check("Alert hides fault", "OOMKilled" not in alert and "oom" not in alert.lower(),
      f"alert='{alert[:80]}'")

# ── TEST 7: Smart agent solves all 5 tasks ──
print("\n" + "=" * 60)
print("TEST 7: Smart Agent Solves All 5 Tasks")
print("=" * 60)
TASKS = {
    "easy_restart": [
        ("investigate", "check_logs", "payment-service", {}),
        ("investigate", "check_metrics", "api-gateway", {}),
        ("diagnose", "submit_diagnosis", "payment-service", {"root_cause": "oom_killed"}),
        ("remediate", "restart", "payment-service", {}),
    ],
    "medium_cascade": [
        ("investigate", "check_logs", "database-primary", {}),
        ("investigate", "check_metrics", "payment-service", {}),
        ("diagnose", "submit_diagnosis", "database-primary", {"root_cause": "connection_pool_exhaustion"}),
        ("remediate", "increase_pool", "database-primary", {"new_max": 500}),
    ],
    "hard_intermittent": [
        ("investigate", "check_metrics", "cache-redis", {}),
        ("investigate", "check_logs", "cache-redis", {}),
        ("diagnose", "submit_diagnosis", "cache-redis", {"root_cause": "cache_fragmentation"}),
        ("remediate", "flush_cache", "cache-redis", {}),
    ],
    "expert_network_partition": [
        ("investigate", "check_logs", "database-replica", {}),
        ("investigate", "check_metrics", "database-replica", {}),
        ("diagnose", "submit_diagnosis", "database-replica", {"root_cause": "network_partition"}),
        ("remediate", "failover", "database-primary", {}),
    ],
    "expert_database_replica_sync": [
        ("investigate", "check_logs", "database-primary", {}),
        ("investigate", "check_metrics", "database-primary", {}),
        ("diagnose", "submit_diagnosis", "database-primary", {"root_cause": "database_replica_sync_failure"}),
        ("remediate", "restart", "database-primary", {}),
    ],
}

for task_id, steps in TASKS.items():
    post("/reset", {"task_id": task_id})
    for atype, cmd, target, params in steps:
        post("/step", {"action_type": atype, "command": cmd, "target": target, "params": params})
    grade = get("/grader")
    check(f"{task_id}", grade["score"] >= 0.7, f"score={grade['score']:.3f}")

# ── SUMMARY ──
print("\n" + "=" * 60)
print(f"RESULTS: {passed} PASSED / {failed} FAILED out of {passed + failed} tests")
print("=" * 60)
if failed == 0:
    print("ALL TESTS PASSED. LIVE DEPLOYMENT IS COMPETITION-READY.")
else:
    print(f"WARNING: {failed} test(s) failed on live deployment!")
