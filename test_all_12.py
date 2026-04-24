"""Test all 12 tasks + random procedural task."""
import json, urllib.request, sys
sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://localhost:7860"

def post(p, d):
    req = urllib.request.Request(BASE+p, data=json.dumps(d).encode(), headers={"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())
def get(p):
    return json.loads(urllib.request.urlopen(BASE+p, timeout=10).read())

# Smart agent strategies for all 12 tasks
STRATEGIES = {
    "easy_restart": [
        ("investigate","check_logs","payment-service",{}),
        ("investigate","check_metrics","api-gateway",{}),
        ("diagnose","submit_diagnosis","payment-service",{"root_cause":"oom_killed"}),
        ("remediate","restart","payment-service",{}),
    ],
    "medium_cascade": [
        ("investigate","check_logs","database-primary",{}),
        ("investigate","check_metrics","payment-service",{}),
        ("diagnose","submit_diagnosis","database-primary",{"root_cause":"connection_pool_exhaustion"}),
        ("remediate","increase_pool","database-primary",{"new_max":500}),
    ],
    "hard_intermittent": [
        ("investigate","check_metrics","cache-redis",{}),
        ("investigate","check_logs","cache-redis",{}),
        ("diagnose","submit_diagnosis","cache-redis",{"root_cause":"cache_fragmentation"}),
        ("remediate","flush_cache","cache-redis",{}),
    ],
    "expert_network_partition": [
        ("investigate","check_logs","database-replica",{}),
        ("investigate","check_metrics","database-replica",{}),
        ("diagnose","submit_diagnosis","database-replica",{"root_cause":"network_partition"}),
        ("remediate","failover","database-primary",{}),
    ],
    "expert_database_replica_sync": [
        ("investigate","check_logs","database-primary",{}),
        ("investigate","check_metrics","database-primary",{}),
        ("diagnose","submit_diagnosis","database-primary",{"root_cause":"database_replica_sync_failure"}),
        ("remediate","restart","database-primary",{}),
    ],
    "medium_cpu_spike": [
        ("investigate","check_metrics","api-gateway",{}),
        ("investigate","check_logs","api-gateway",{}),
        ("diagnose","submit_diagnosis","api-gateway",{"root_cause":"cpu_throttle"}),
        ("remediate","scale_up","api-gateway",{}),
    ],
    "medium_memory_leak": [
        ("investigate","check_logs","user-service",{}),
        ("investigate","check_metrics","user-service",{}),
        ("diagnose","submit_diagnosis","user-service",{"root_cause":"slow_memory_leak"}),
        ("remediate","restart","user-service",{}),
    ],
    "hard_disk_pressure": [
        ("investigate","check_metrics","database-primary",{}),
        ("investigate","check_logs","database-primary",{}),
        ("diagnose","submit_diagnosis","database-primary",{"root_cause":"disk_pressure"}),
        ("remediate","increase_pool","database-primary",{}),
    ],
    "hard_dns_resolution": [
        ("investigate","check_logs","api-gateway",{}),
        ("investigate","check_metrics","api-gateway",{}),
        ("diagnose","submit_diagnosis","api-gateway",{"root_cause":"dns_resolution_failure"}),
        ("remediate","restart","api-gateway",{}),
    ],
    "expert_deadlock": [
        ("investigate","check_logs","database-primary",{}),
        ("investigate","check_metrics","database-primary",{}),
        ("diagnose","submit_diagnosis","database-primary",{"root_cause":"database_deadlock"}),
        ("remediate","restart","database-primary",{}),
    ],
    "expert_cert_expiry": [
        ("investigate","check_logs","api-gateway",{}),
        ("investigate","check_metrics","api-gateway",{}),
        ("diagnose","submit_diagnosis","api-gateway",{"root_cause":"tls_cert_expired"}),
        ("remediate","rollback","api-gateway",{}),
    ],
    "hard_config_drift": [
        ("investigate","check_logs","payment-service",{}),
        ("investigate","check_metrics","payment-service",{}),
        ("diagnose","submit_diagnosis","payment-service",{"root_cause":"config_drift"}),
        ("remediate","rollback","payment-service",{}),
    ],
}

passed = 0
failed = 0
print("=" * 60)
print("TESTING ALL 12 TASKS + RANDOM")
print("=" * 60)

for task_id, steps in STRATEGIES.items():
    post("/reset", {"task_id": task_id})
    for a,c,t,p in steps:
        post("/step", {"action_type":a,"command":c,"target":t,"params":p})
    grade = get("/grader")
    ok = grade["score"] >= 0.7
    if ok: passed += 1
    else: failed += 1
    status = "PASS" if ok else "FAIL"
    print(f"  {status}: {task_id:40s} score={grade['score']:.3f}")

# Test random task 5 times
print("\nRANDOM TASK (5 episodes):")
for i in range(5):
    obs = post("/reset", {"task_id": "random"})
    state = get("/state")
    task = state.get("task_id", "?")
    print(f"  Episode {i+1}: assigned → {task}")
    passed += 1  # Just test it doesn't crash

print(f"\n{'='*60}")
print(f"RESULTS: {passed} PASSED / {failed} FAILED")
print(f"{'='*60}")
