#!/usr/bin/env python3
"""Baseline inference script for SREBench environment."""
import os
import sys
import json
import requests
from typing import Dict, List

ENV_URL = os.getenv("ENV_URL", "http://localhost:8000")


def format_observation(obs: Dict) -> str:
    """Format observation for LLM."""
    dashboard = obs.get("system_dashboard", [])
    
    dashboard_str = "SERVICE            STATUS      CPU    MEM    ERR_RATE   LATENCY_P99\n"
    for svc in dashboard:
        dashboard_str += f"{svc['name']:<18}{svc['status']:<12}{svc['cpu_percent']:>5.1f}%  {svc['memory_percent']:>5.1f}%  {svc['error_rate_percent']:>6.1f}%    {svc['latency_p99_ms']:>6.0f}ms\n"
    
    return f"""=== INCIDENT ALERT ===
{obs.get('alert_message', 'Alert pending...')}

=== SYSTEM DASHBOARD ===
{dashboard_str}

=== LAST ACTION RESULT ===
{obs.get('last_action_result', '[No actions yet]')}

=== STATUS ===
Steps taken: {obs.get('steps_taken', 0)}/{obs.get('max_steps', 30)}
SLA remaining: {obs.get('sla_remaining_minutes', 30):.1f} minutes
"""


def run_episode(task_id: str) -> Dict:
    """Run a single episode with simple baseline strategy."""
    print(f"\n{'='*60}")
    print(f"Running task: {task_id}")
    print(f"{'='*60}")
    
    # Reset
    resp = requests.post(f"{ENV_URL}/reset", json={"task_id": task_id})
    if resp.status_code != 200:
        print(f"Failed to reset: {resp.status_code} {resp.text}")
        return {"task_id": task_id, "error": "reset_failed"}
    
    obs = resp.json()
    done = False
    step_count = 0
    actions_log = []
    
    print("\n" + format_observation(obs))
    
    # Baseline strategy: investigate -> diagnose -> remediate
    investigation_steps = 0
    max_investigation = 5
    
    while not done and step_count < 30:
        step_count += 1
        
        # Find unhealthy services
        degraded = [s for s in obs.get("system_dashboard", []) if s["status"] != "healthy"]
        
        if not degraded:
            print("\n✓ All services healthy! Incident resolved.")
            done = True
            break
        
        # Strategy based on phase
        if investigation_steps < max_investigation:
            # Investigate phase
            target = degraded[0]["name"]
            investigation_steps += 1
            
            if investigation_steps <= 2:
                action = {
                    "action_type": "investigate",
                    "command": "check_logs",
                    "target": target,
                    "params": {"severity": "ERROR", "last_n": 15},
                }
                print(f"\n[Step {step_count}] Checking logs on {target}...")
            else:
                action = {
                    "action_type": "investigate",
                    "command": "check_metrics",
                    "target": target,
                    "params": {"metric": "all"},
                }
                print(f"\n[Step {step_count}] Checking metrics on {target}...")
        
        else:
            # Diagnosis phase
            last_result = obs.get("last_action_result", "").lower()
            
            # Infer root cause from logs/metrics
            if "memory" in last_result or "oom" in last_result:
                action = {
                    "action_type": "diagnose",
                    "command": "submit_diagnosis",
                    "target": "payment-service",
                    "params": {"root_cause": "oom_killed"},
                }
                print(f"\n[Step {step_count}] Diagnosing: OOM (memory exhaustion detected)")
            elif "connection" in last_result or "pool" in last_result:
                action = {
                    "action_type": "diagnose",
                    "command": "submit_diagnosis",
                    "target": "database-primary",
                    "params": {"root_cause": "connection_pool_exhaustion"},
                }
                print(f"\n[Step {step_count}] Diagnosing: Connection pool exhaustion")
            elif "cache" in last_result or "fragmentation" in last_result or "eviction" in last_result:
                action = {
                    "action_type": "diagnose",
                    "command": "submit_diagnosis",
                    "target": "cache-redis",
                    "params": {"root_cause": "cache_fragmentation"},
                }
                print(f"\n[Step {step_count}] Diagnosing: Cache fragmentation")
            else:
                # Fallback diagnosis
                action = {
                    "action_type": "diagnose",
                    "command": "submit_diagnosis",
                    "target": degraded[0]["name"],
                    "params": {"root_cause": "service_overload"},
                }
                print(f"\n[Step {step_count}] Diagnosing: Service overload (fallback)")
            
            investigation_steps = max_investigation + 10  # Move to remediation
        
        # Execute action
        try:
            resp = requests.post(f"{ENV_URL}/step", json=action)
            if resp.status_code != 200:
                print(f"  Error: {resp.status_code}")
                break
            
            result = resp.json()
            obs = result.get("observation", {})
            reward = result.get("reward", {}).get("value", 0.0)
            done = result.get("done", False)
            
            actions_log.append({
                "step": step_count,
                "action": action,
                "reward": reward,
            })
            
            print(f"  Reward: {reward:+.3f}")
            
            # Check if ready to remediate
            if investigation_steps >= max_investigation + 1:
                investigation_steps = max_investigation + 10
                print("\n[Remediation Phase]")
                
                # Apply fixes based on diagnosis
                if "oom" in action.get("params", {}).get("root_cause", "").lower():
                    fix_action = {
                        "action_type": "remediate",
                        "command": "restart",
                        "target": "payment-service",
                        "params": {},
                    }
                elif "connection" in action.get("params", {}).get("root_cause", "").lower():
                    fix_action = {
                        "action_type": "remediate",
                        "command": "increase_pool",
                        "target": "database-primary",
                        "params": {"new_max": 500},
                    }
                elif "cache" in action.get("params", {}).get("root_cause", "").lower():
                    fix_action = {
                        "action_type": "remediate",
                        "command": "flush_cache",
                        "target": "cache-redis",
                        "params": {},
                    }
                else:
                    fix_action = {
                        "action_type": "remediate",
                        "command": "restart",
                        "target": degraded[0]["name"],
                        "params": {},
                    }
                
                # Take fix action
                step_count += 1
                resp = requests.post(f"{ENV_URL}/step", json=fix_action)
                if resp.status_code == 200:
                    result = resp.json()
                    obs = result.get("observation", {})
                    reward = result.get("reward", {}).get("value", 0.0)
                    done = result.get("done", False)
                    actions_log.append({
                        "step": step_count,
                        "action": fix_action,
                        "reward": reward,
                    })
                    print(f"\n[Step {step_count}] Remediating: {fix_action['command']} on {fix_action['target']}")
                    print(f"  Reward: {reward:+.3f}")
        
        except Exception as e:
            print(f"  Exception: {e}")
            break
    
    # Get final grade
    try:
        grade_resp = requests.get(f"{ENV_URL}/grader", params={"task_id": task_id})
        if grade_resp.status_code == 200:
            grade_data = grade_resp.json()
            score = grade_data.get("score", 0.0)
        else:
            score = 0.0
    except:
        score = 0.0
    
    print(f"\n{'='*60}")
    print(f"Episode completed in {step_count} steps")
    print(f"Final score: {score:.3f}")
    print(f"{'='*60}")
    
    return {
        "task_id": task_id,
        "score": score,
        "steps": step_count,
        "actions": len(actions_log),
    }


def main():
    """Run baseline on all tasks."""
    print("\nSREBench Baseline Evaluation")
    print("=" * 60)
    
    # Check if environment is running
    try:
        resp = requests.get(f"{ENV_URL}/", timeout=5)
        if resp.status_code != 200:
            print(f"Error: Environment not responding at {ENV_URL}")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print(f"Error: Cannot connect to environment at {ENV_URL}")
        print("Make sure the environment is running: uvicorn src.server:app --host 0.0.0.0 --port 8000")
        sys.exit(1)
    
    tasks = ["easy_restart", "medium_cascade", "hard_intermittent"]
    results = []
    
    for task in tasks:
        result = run_episode(task)
        results.append(result)
    
    # Summary
    print("\n" + "="*60)
    print("BASELINE SUMMARY")
    print("="*60)
    for result in results:
        print(f"{result['task_id']:<20} Score: {result['score']:.3f} (Steps: {result['steps']})")
    
    avg_score = sum(r["score"] for r in results) / len(results)
    print(f"\nAverage score: {avg_score:.3f}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
