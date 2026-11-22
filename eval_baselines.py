#!/usr/bin/env python3
"""
SREBench Baseline Evaluation Suite
Runs Random, Heuristic Triage, and Oracle Upper Bound baselines
across all 12 tasks (50 seeds each) + 50 procedural compound tasks.
Generates results/baseline_receipts.json.
"""

import sys
import os
import json
import time
import random
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

# Add sre-bench directory to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent / "sre-bench"))

from src.environment import SREBenchEnvironment, INCIDENTS
from src.models import IncidentAction

SERVICES = [
    "api-gateway",
    "user-service",
    "payment-service",
    "database-primary",
    "database-replica",
    "cache-redis",
]

# Topological depth: deep infrastructure / storage dependencies first
SERVICE_TOPOLOGY_DEPTH = {
    "database-primary": 0,
    "cache-redis": 0,
    "database-replica": 1,
    "payment-service": 2,
    "user-service": 2,
    "api-gateway": 3,
}

TASK_LIST = list(INCIDENTS.keys())

ALL_FAULTS = [
    "oom_killed",
    "connection_pool_exhaustion",
    "cache_fragmentation",
    "network_partition",
    "database_replica_sync_failure",
    "cpu_throttle",
    "slow_memory_leak",
    "disk_pressure",
    "dns_resolution_failure",
    "database_deadlock",
    "tls_cert_expired",
    "config_drift",
]

FAULT_SIGNATURES = {
    "oom_killed": [r"oom", r"exit code 137", r"heap space", r"outofmemoryerror"],
    "connection_pool_exhaustion": [r"pool exhausted", r"connectiontimeout", r"pool utilization", r"cannot acquire connection"],
    "cache_fragmentation": [r"fragmentation", r"frag_ratio", r"cache hit ratio", r"evicting key"],
    "network_partition": [r"cannot reach database-primary", r"replication lag detected", r"replica-primary link", r"partition"],
    "database_replica_sync_failure": [r"wal sync failed", r"replica sync lag", r"replica cannot connect", r"cannot ensure replica durability"],
    "cpu_throttle": [r"cpu throttling", r"throttle_pct", r"request queue depth", r"thread pool saturated"],
    "slow_memory_leak": [r"heap usage", r"resident memory growing", r"gc frequency increasing", r"finalizer queue depth"],
    "disk_pressure": [r"disk usage", r"no space left on device", r"wal segment accumulation", r"checkpoint failed"],
    "dns_resolution_failure": [r"dns resolution failed", r"servfail", r"dns lookup delay"],
    "database_deadlock": [r"deadlock", r"deadlock_count", r"deadlock detected", r"cascading transaction"],
    "tls_cert_expired": [r"tls cert expired", r"cert_days_expired", r"certificate", r"expired tls", r"ssl_error", r"handshake failed"],
    "config_drift": [r"config drift", r"config hash", r"hash mismatch", r"feature flag", r"rate limiter threshold", r"unexpected 503", r"config reload", r"reload_time"],
}

FAULT_TO_FIX = {
    "oom_killed": ("restart", {}),
    "connection_pool_exhaustion": ("increase_pool", {"new_max": 500}),
    "cache_fragmentation": ("flush_cache", {}),
    "network_partition": ("failover", {}),
    "database_replica_sync_failure": ("restart", {}),
    "cpu_throttle": ("scale_up", {}),
    "slow_memory_leak": ("restart", {}),
    "disk_pressure": ("increase_pool", {}),
    "dns_resolution_failure": ("restart", {}),
    "database_deadlock": ("restart", {}),
    "tls_cert_expired": ("rollback", {}),
    "config_drift": ("rollback", {}),
}

RELATED_SERVICES = {
    "payment-service": "api-gateway",
    "database-primary": "payment-service",
    "cache-redis": "payment-service",
    "database-replica": "database-primary",
    "api-gateway": "payment-service",
    "user-service": "api-gateway",
}


class RandomAgent:
    """Agent that selects uniformly random valid actions."""

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.action_types = ["investigate", "diagnose", "remediate"]
        self.investigate_cmds = ["check_logs", "check_metrics", "check_connections"]
        self.remediate_cmds = ["restart", "scale_up", "increase_pool", "flush_cache", "rollback", "failover"]

    def act(self, obs, env) -> IncidentAction:
        atype = self.rng.choice(self.action_types)
        target = self.rng.choice(SERVICES)
        if atype == "investigate":
            cmd = self.rng.choice(self.investigate_cmds)
            params = {}
        elif atype == "diagnose":
            cmd = "submit_diagnosis"
            params = {"root_cause": self.rng.choice(ALL_FAULTS)}
        else:
            cmd = self.rng.choice(self.remediate_cmds)
            params = {"new_max": 500} if cmd == "increase_pool" else {}
        return IncidentAction(action_type=atype, command=cmd, target=target, params=params)


class HeuristicTriageAgent:
    """
    Realistic SRE triage heuristic agent:
    1. Inspects dashboard alerts and prioritizes deep dependency bottlenecks.
    2. Investigates >= 2 distinct targets (e.g. root suspect + dependent/upstream service)
       to satisfy anti-exploit threshold and prevent premature diagnosis penalty (-0.15).
    3. Analyzes telemetry & logs to classify root causes via signature matching.
    4. Diagnoses root cause and executes corresponding remediation.
    5. Iterates across remaining degraded services in compound scenarios.
    """

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.investigated: List[str] = []
        self.diagnosed_roots: List[str] = []
        self.remediated_roots: List[str] = []
        self.suspect_queue: List[str] = []
        self.current_suspect: str = ""
        self.detected_faults: Dict[str, str] = {}

    def reset(self):
        self.investigated = []
        self.diagnosed_roots = []
        self.remediated_roots = []
        self.suspect_queue = []
        self.current_suspect = ""
        self.detected_faults = {}

    def _match_log_fault(self, text: str) -> Optional[str]:
        text_lower = text.lower()
        for fault, patterns in FAULT_SIGNATURES.items():
            for pat in patterns:
                if re.search(pat, text_lower):
                    return fault
        return None

    def _build_suspect_queue(self, obs) -> List[str]:
        degraded = [s.name for s in obs.system_dashboard if s.status != "healthy"]
        # Sort degraded services by dependency depth (deepest first: database-primary, cache-redis, etc.)
        sorted_degraded = sorted(degraded, key=lambda s: SERVICE_TOPOLOGY_DEPTH.get(s, 99))

        # Check for subtle symptoms (e.g. cache-redis or user-service creeping memory even if status is healthy)
        for s in obs.system_dashboard:
            if s.name == "user-service" and s.memory_percent > 75.0 and "user-service" not in sorted_degraded:
                sorted_degraded.append("user-service")
            elif s.name == "cache-redis" and "cache-redis" not in sorted_degraded and any(d in ["payment-service", "user-service"] for d in degraded):
                # If payment or user degraded, cache-redis is a prime candidate
                sorted_degraded.append("cache-redis")

        if not sorted_degraded:
            sorted_degraded = ["api-gateway"]
        return sorted_degraded

    def act(self, obs, env) -> IncidentAction:
        if not self.suspect_queue:
            self.suspect_queue = self._build_suspect_queue(obs)

        if not self.current_suspect:
            self.current_suspect = self.suspect_queue[0]

        # Check last action result for fault signatures on the last investigated target
        if obs.last_action_result and self.investigated:
            last_target = self.investigated[-1]
            fault = self._match_log_fault(obs.last_action_result)
            if fault:
                self.detected_faults[last_target] = fault

        # 1. Ensure at least 2 distinct services are investigated before diagnosis
        if len(self.investigated) < 2:
            if not self.investigated:
                target = self.current_suspect
                self.investigated.append(target)
                return IncidentAction(action_type="investigate", command="check_logs", target=target, params={})
            else:
                # Pick second distinct service
                candidates = [s for s in self.suspect_queue if s not in self.investigated]
                if candidates:
                    second = candidates[0]
                else:
                    second = RELATED_SERVICES.get(self.investigated[0], "api-gateway")
                    if second in self.investigated:
                        for s in SERVICES:
                            if s not in self.investigated:
                                second = s
                                break
                self.investigated.append(second)
                return IncidentAction(action_type="investigate", command="check_logs", target=second, params={})

        # Check if we have detected a fault on our current suspect
        suspect = self.current_suspect
        fault = self.detected_faults.get(suspect)

        # If fault not found on current suspect, investigate suspect logs if not investigated yet
        if not fault and suspect not in self.investigated:
            self.investigated.append(suspect)
            return IncidentAction(action_type="investigate", command="check_logs", target=suspect, params={})

        # If fault still not found, check other investigated targets
        if not fault:
            for inv_target, f in self.detected_faults.items():
                if inv_target not in self.remediated_roots:
                    suspect = inv_target
                    fault = f
                    self.current_suspect = suspect
                    break

        # Fallback if no fault matched in logs
        if not fault:
            # Check if any service in queue has logs we haven't seen
            unseen = [s for s in self.suspect_queue if s not in self.investigated]
            if unseen:
                target = unseen[0]
                self.investigated.append(target)
                self.current_suspect = target
                return IncidentAction(action_type="investigate", command="check_logs", target=target, params={})
            fault = "cpu_throttle"

        # 2. Submit diagnosis
        if suspect not in self.diagnosed_roots:
            self.diagnosed_roots.append(suspect)
            return IncidentAction(
                action_type="diagnose",
                command="submit_diagnosis",
                target=suspect,
                params={"root_cause": fault},
            )

        # 3. Apply remediation
        if suspect not in self.remediated_roots:
            self.remediated_roots.append(suspect)
            cmd, params = FAULT_TO_FIX.get(fault, ("restart", {}))
            return IncidentAction(action_type="remediate", command=cmd, target=suspect, params=params)

        # 4. If still degraded, advance to next suspect in queue
        degraded = [s.name for s in obs.system_dashboard if s.status != "healthy"]
        remaining = [s for s in degraded if s not in self.remediated_roots]
        if remaining:
            self.current_suspect = remaining[0]
            if self.current_suspect not in self.investigated:
                self.investigated.append(self.current_suspect)
                return IncidentAction(action_type="investigate", command="check_logs", target=self.current_suspect, params={})

        # Fallback verification step
        return IncidentAction(action_type="investigate", command="check_metrics", target="api-gateway", params={})


class OracleAgent:
    """
    Theoretical Upper Bound:
    Has perfect knowledge of the incident configuration and executes
    the minimal, optimal sequence:
    1. Investigate root cause(s).
    2. Investigate secondary related service (to satisfy >= 2 distinct targets).
    3. Submit exact ground truth diagnosis.
    4. Apply exact ground truth remediation.
    """

    def __init__(self):
        self.step_idx = 0
        self.plan: List[IncidentAction] = []

    def reset_plan(self, env):
        self.step_idx = 0
        self.plan = []
        cfg = env.current_incident_config

        if cfg.get("is_compound", False):
            # Compound incident
            configs = cfg.get("configurations", [])
            all_roots = [c["root_cause_service"] for c in configs]
            # 1. Investigate all root cause services
            for root in all_roots:
                self.plan.append(IncidentAction(action_type="investigate", command="check_logs", target=root, params={}))
            # If only 1 root in compound, investigate related
            if len(all_roots) < 2:
                rel = RELATED_SERVICES.get(all_roots[0], "api-gateway")
                self.plan.append(IncidentAction(action_type="investigate", command="check_metrics", target=rel, params={}))
            # 2. Diagnoses
            all_faults = [c["fault_type"] for c in configs]
            combined_diag = " ".join(all_faults)
            self.plan.append(IncidentAction(
                action_type="diagnose",
                command="submit_diagnosis",
                target=all_roots[0],
                params={"root_cause": combined_diag},
            ))
            # 3. Remediations
            for c in configs:
                root = c["root_cause_service"]
                fix = c["ground_truth_fix"]
                params = {"new_max": 500} if fix == "increase_pool" else {}
                self.plan.append(IncidentAction(action_type="remediate", command=fix, target=root, params=params))
        else:
            # Single incident
            root = cfg["root_cause_service"]
            fault = cfg["ground_truth_diagnosis"]
            fix = cfg["ground_truth_fix"]
            rel = RELATED_SERVICES.get(root, "api-gateway")
            if rel == root:
                rel = "database-primary" if root != "database-primary" else "payment-service"

            # Step 1: investigate root
            self.plan.append(IncidentAction(action_type="investigate", command="check_logs", target=root, params={}))
            # Step 2: investigate related service (satisfies len(investigated_targets) >= 2)
            self.plan.append(IncidentAction(action_type="investigate", command="check_metrics", target=rel, params={}))
            # Step 3: submit diagnosis
            self.plan.append(IncidentAction(
                action_type="diagnose",
                command="submit_diagnosis",
                target=root,
                params={"root_cause": fault},
            ))
            # Step 4: remediate root cause
            params = {"new_max": 500} if fix == "increase_pool" else {}
            self.plan.append(IncidentAction(action_type="remediate", command=fix, target=root, params=params))

    def act(self, obs, env) -> IncidentAction:
        if self.step_idx < len(self.plan):
            act = self.plan[self.step_idx]
            self.step_idx += 1
            return act
        return IncidentAction(action_type="investigate", command="check_metrics", target="api-gateway", params={})


def run_single_episode(agent, env, task_id: str, seed: int, is_compound: bool = False, compound_state: Dict = None) -> Dict[str, Any]:
    """Execute a single episode and return metrics."""
    env.episode_id = f"eval_{seed:05d}"
    if is_compound and compound_state:
        obs = env._apply_compound_faults(compound_state)
    else:
        obs = env.reset(task_id)

    # Deterministic infrastructure seed for exact reproducibility across runs
    from src.infrastructure import Infrastructure
    env.infrastructure = Infrastructure(seed=seed)
    env.infrastructure.inject_incident(env.current_incident_config)

    if hasattr(agent, "reset"):
        agent.reset()
    if hasattr(agent, "reset_plan"):
        agent.reset_plan(env)

    done = False
    step_count = 0
    max_steps = env.max_steps
    episode_reward = 0.0

    while not done and step_count < max_steps:
        action = agent.act(obs, env)
        obs, reward_obj, done, info = env.step(action)
        episode_reward += reward_obj.value
        step_count += 1
        if env._check_incident_resolved():
            done = True

    resolved = env._check_incident_resolved()
    return {
        "task_id": task_id,
        "seed": seed,
        "resolved": resolved,
        "steps": step_count,
        "cumulative_reward": episode_reward,
        "final_reward": env.cumulative_reward,
    }


def evaluate_agent(agent_name: str, agent_factory, num_seeds: int = 50) -> Dict[str, Any]:
    """Evaluate an agent across all 12 tasks (num_seeds each) + compound procedural tasks."""
    env = SREBenchEnvironment()
    results_by_task: Dict[str, List[Dict[str, Any]]] = {t: [] for t in TASK_LIST}
    compound_results: List[Dict[str, Any]] = []

    start_time = time.time()
    total_episodes = 0

    # 1. Standard 12 tasks
    for task_id in TASK_LIST:
        for s in range(num_seeds):
            agent = agent_factory(seed=s + 1000)
            res = run_single_episode(agent, env, task_id, seed=s + 1000)
            results_by_task[task_id].append(res)
            total_episodes += 1

    # 2. 50 Procedural compound tasks
    compound_rng = random.Random(9999)
    available_procedural_faults = ["cpu_throttle", "memory_leak", "connection_drop", "disk_io_spike", "cache_fragmentation"]

    for s in range(num_seeds):
        agent = agent_factory(seed=s + 5000)
        n_targets = compound_rng.choice([2, 3])
        targets = compound_rng.sample(SERVICES, n_targets)
        c_state = {t: compound_rng.choice(available_procedural_faults) for t in targets}
        res = run_single_episode(agent, env, "procedural_compound", seed=s + 5000, is_compound=True, compound_state=c_state)
        compound_results.append(res)
        total_episodes += 1

    elapsed_time = time.time() - start_time
    episodes_per_sec = total_episodes / max(elapsed_time, 0.0001)

    # Aggregate stats
    all_episodes = [ep for task_eps in results_by_task.values() for ep in task_eps] + compound_results
    rewards = [ep["final_reward"] for ep in all_episodes]
    steps = [ep["steps"] for ep in all_episodes]
    pass_count = sum(1 for ep in all_episodes if ep["resolved"])

    mean_reward = sum(rewards) / len(rewards)
    variance_reward = sum((r - mean_reward) ** 2 for r in rewards) / len(rewards)
    std_reward = variance_reward ** 0.5
    pass_rate = pass_count / len(all_episodes)
    mean_steps = sum(steps) / len(steps)

    # Per task breakdown
    task_breakdown = {}
    for task_id, eps in results_by_task.items():
        t_rewards = [e["final_reward"] for e in eps]
        t_steps = [e["steps"] for e in eps]
        t_pass = sum(1 for e in eps if e["resolved"])
        t_mean_r = sum(t_rewards) / len(t_rewards)
        t_std_r = (sum((r - t_mean_r) ** 2 for r in t_rewards) / len(t_rewards)) ** 0.5
        task_breakdown[task_id] = {
            "mean_reward": round(t_mean_r, 4),
            "std_reward": round(t_std_r, 4),
            "pass_rate": round(t_pass / len(eps), 4),
            "mean_steps": round(sum(t_steps) / len(t_steps), 2),
            "episodes": len(eps),
        }

    c_rewards = [e["final_reward"] for e in compound_results]
    c_steps = [e["steps"] for e in compound_results]
    c_pass = sum(1 for e in compound_results if e["resolved"])
    c_mean_r = sum(c_rewards) / len(c_rewards)
    c_std_r = (sum((r - c_mean_r) ** 2 for r in c_rewards) / len(c_rewards)) ** 0.5
    task_breakdown["procedural_compound"] = {
        "mean_reward": round(c_mean_r, 4),
        "std_reward": round(c_std_r, 4),
        "pass_rate": round(c_pass / len(compound_results), 4),
        "mean_steps": round(sum(c_steps) / len(c_steps), 2),
        "episodes": len(compound_results),
    }

    return {
        "agent": agent_name,
        "total_episodes": total_episodes,
        "elapsed_seconds": round(elapsed_time, 3),
        "episodes_per_sec": round(episodes_per_sec, 2),
        "mean_reward": round(mean_reward, 4),
        "std_reward": round(std_reward, 4),
        "pass_rate": round(pass_rate, 4),
        "mean_steps_to_resolution": round(mean_steps, 2),
        "task_breakdown": task_breakdown,
    }


def main():
    print("=" * 70)
    print("SREBench Baseline Evaluation: Random vs Heuristic vs Oracle")
    print("50 seeds x 12 standard tasks + 50 procedural compound tasks (650 eps/agent)")
    print("=" * 70)

    agents = [
        ("Random Agent", lambda seed: RandomAgent(seed=seed)),
        ("Heuristic Triage Agent", lambda seed: HeuristicTriageAgent(seed=seed)),
        ("Oracle Upper Bound", lambda seed: OracleAgent()),
    ]

    receipts = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environment": "SREBench-v1.0",
        "num_tasks": 12,
        "num_compound_tasks": 50,
        "seeds_per_task": 50,
        "total_episodes_per_agent": 650,
        "baselines": {},
    }

    for name, factory in agents:
        print(f"\nEvaluating {name}...")
        res = evaluate_agent(name, factory, num_seeds=50)
        receipts["baselines"][name] = res
        print(f"  Mean Reward : {res['mean_reward']:+.4f} (std: {res['std_reward']:.4f})")
        print(f"  Pass Rate   : {res['pass_rate'] * 100:.1f}%")
        print(f"  Mean Steps  : {res['mean_steps_to_resolution']:.2f}")
        print(f"  Throughput  : {res['episodes_per_sec']:.1f} episodes/sec")

    # Save to results/baseline_receipts.json
    out_dir = Path(__file__).resolve().parent / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "baseline_receipts.json"

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(receipts, f, indent=2)

    print(f"\n[OK] Baseline evaluation receipts saved to {out_file}")
    print("=" * 70)


if __name__ == "__main__":
    main()
