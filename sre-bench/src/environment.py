"""Main SREBench environment."""
import uuid
from typing import Tuple, Dict
from .models import (
    IncidentAction, IncidentObservation, IncidentReward, 
    IncidentState, ServiceStatus
)
from .infrastructure import Infrastructure


INCIDENTS = {
    "easy_restart": {
        "root_cause_service": "payment-service",
        "fault_type": "oom_killed",
        "ground_truth_diagnosis": "oom_killed",
        "ground_truth_fix": "restart",
        "description": "payment-service OOMKilled due to memory leak",
        "max_steps": 30,
    },
    "medium_cascade": {
        "root_cause_service": "database-primary",
        "fault_type": "connection_pool_exhaustion",
        "ground_truth_diagnosis": "connection_pool_exhaustion",
        "ground_truth_fix": "increase_pool",
        "description": "database connection pool exhausted causing cascading timeouts",
        "max_steps": 30,
    },
    "hard_intermittent": {
        "root_cause_service": "cache-redis",
        "fault_type": "cache_fragmentation",
        "ground_truth_diagnosis": "cache_fragmentation",
        "ground_truth_fix": "flush_cache",
        "description": "Subtle cache fragmentation causing intermittent fallback to DB",
        "max_steps": 30,
    },
    "expert_network_partition": {
        "root_cause_service": "database-replica",
        "fault_type": "network_partition",
        "ground_truth_diagnosis": "network_partition",
        "ground_truth_fix": "failover",
        "description": "Network partition between primary and replica causing replication lag",
        "max_steps": 35,
    },
    "expert_database_replica_sync": {
        "root_cause_service": "database-primary",
        "fault_type": "database_replica_sync_failure",
        "ground_truth_diagnosis": "database_replica_sync_failure",
        "ground_truth_fix": "restart",
        "description": "Database replica sync failure causing data inconsistency",
        "max_steps": 35,
    },
    "medium_cpu_spike": {
        "root_cause_service": "api-gateway",
        "fault_type": "cpu_throttle",
        "ground_truth_diagnosis": "cpu_throttle",
        "ground_truth_fix": "scale_up",
        "description": "CPU saturation on API gateway causing request queuing and timeouts",
        "max_steps": 30,
    },
    "medium_memory_leak": {
        "root_cause_service": "user-service",
        "fault_type": "slow_memory_leak",
        "ground_truth_diagnosis": "slow_memory_leak",
        "ground_truth_fix": "restart",
        "description": "Gradual memory leak in user-service causing increasing GC pressure",
        "max_steps": 30,
    },
    "hard_disk_pressure": {
        "root_cause_service": "database-primary",
        "fault_type": "disk_pressure",
        "ground_truth_diagnosis": "disk_pressure",
        "ground_truth_fix": "increase_pool",
        "description": "Disk I/O bottleneck on database-primary from WAL accumulation",
        "max_steps": 30,
    },
    "hard_dns_resolution": {
        "root_cause_service": "api-gateway",
        "fault_type": "dns_resolution_failure",
        "ground_truth_diagnosis": "dns_resolution_failure",
        "ground_truth_fix": "restart",
        "description": "DNS resolution failure making all downstream services unreachable",
        "max_steps": 30,
    },
    "expert_deadlock": {
        "root_cause_service": "database-primary",
        "fault_type": "database_deadlock",
        "ground_truth_diagnosis": "database_deadlock",
        "ground_truth_fix": "restart",
        "description": "Database deadlock causing cascading transaction timeouts",
        "max_steps": 35,
    },
    "expert_cert_expiry": {
        "root_cause_service": "api-gateway",
        "fault_type": "tls_cert_expired",
        "ground_truth_diagnosis": "tls_cert_expired",
        "ground_truth_fix": "rollback",
        "description": "Expired TLS certificate rejecting all client connections",
        "max_steps": 35,
    },
    "hard_config_drift": {
        "root_cause_service": "payment-service",
        "fault_type": "config_drift",
        "ground_truth_diagnosis": "config_drift",
        "ground_truth_fix": "rollback",
        "description": "Configuration drift after bad deploy causing intermittent 503 errors",
        "max_steps": 30,
    },
}


class SREBenchEnvironment:
    """OpenEnv-compliant environment for SRE incident response."""
    
    def __init__(self):
        self.infrastructure = None
        self.episode_id = ""
        self.task_id = ""
        self.step_count = 0
        self.max_steps = 30
        self.diagnosis_submitted = None
        self.correct_diagnosis = False
        self.cumulative_reward = 0.0
        self.actions_taken = []
        self.last_action_result = ""
        self.sla_remaining_minutes = 30.0

        # Episode-level behavior tracking for anti-exploit and richer rewards.
        self.investigated_targets = set()
        self.restart_targets = set()
        self.failed_remediations = 0
        self.shotgun_penalty_applied = False
        
        # Solution caching for reproducibility
        self.solution_cache = {}  # {task_id: {'steps': int, 'reward': float, 'actions': list}}
        self.resolution_step = None  # Step number when incident first resolved
    
    def reset(self, task_id: str = "easy_restart") -> IncidentObservation:
        """Reset environment to initial state."""
        self.episode_id = str(uuid.uuid4())[:8]
        self.task_id = task_id
        self.step_count = 0
        self.max_steps = 30
        self.diagnosis_submitted = None
        self.correct_diagnosis = False
        self.cumulative_reward = 0.0
        self.actions_taken = []
        self.sla_remaining_minutes = 30.0
        self.investigated_targets = set()
        self.restart_targets = set()
        self.failed_remediations = 0
        self.shotgun_penalty_applied = False
        
        # Create new infrastructure and inject incident
        # Support procedural "random" task — pick a random incident each episode
        import random as _rng
        if task_id == "random":
            real_task = _rng.choice([k for k in INCIDENTS.keys()])
            self.task_id = real_task
            incident_config = INCIDENTS[real_task]
        else:
            incident_config = INCIDENTS.get(task_id, INCIDENTS["easy_restart"])
        self.infrastructure = Infrastructure(seed=hash(self.episode_id) % (2**31))
        self.infrastructure.inject_incident(incident_config)
        self.max_steps = incident_config.get("max_steps", 30)
        
        # Generate initial observation — do NOT reveal the fault type
        self.last_action_result = f"Incident detected: Service degradation reported. Multiple alerts firing. Begin investigation."
        return self._make_observation()
    
    def step(self, action: IncidentAction) -> Tuple[IncidentObservation, IncidentReward, bool, Dict]:
        """Take one step in the environment."""
        self.step_count += 1
        self.sla_remaining_minutes = max(0, 30.0 - (self.step_count * 1.0))
        
        reward_value = 0.0
        reward_breakdown = {}
        
        # Handle give_up
        if action.action_type == "give_up":
            reward_value = -0.5
            done = True
            return self._make_observation(), IncidentReward(
                value=reward_value, 
                breakdown={"action": "give_up"},
                episode_id=self.episode_id
            ), done, {}
        
        # Execute action
        self.last_action_result = self.infrastructure.execute_action(action)
        self.actions_taken.append(f"{action.action_type}:{action.command}:{action.target}")
        
        # Calculate reward
        reward_value, reward_breakdown = self._calculate_reward(action)
        self.cumulative_reward += reward_value
        
        # Check if incident is resolved
        incident_resolved = self._check_incident_resolved()
        
        # Cache solution on first resolution (for reproducibility)
        if incident_resolved and self.resolution_step is None:
            self.resolution_step = self.step_count
            self.solution_cache[self.task_id] = {
                'steps': self.step_count,
                'cumulative_reward': self.cumulative_reward,
                'actions': self.actions_taken.copy(),
                'diagnosis': self.diagnosis_submitted,
            }
        
        # Check termination conditions
        done = incident_resolved or self.step_count >= self.max_steps or self.sla_remaining_minutes <= 0
        
        return (
            self._make_observation(),
            IncidentReward(value=reward_value, breakdown=reward_breakdown, episode_id=self.episode_id),
            done,
            {"incident_resolved": incident_resolved, "steps_to_resolution": self.resolution_step}
        )
    
    def state(self) -> IncidentState:
        """Return full internal state."""
        incident_config = INCIDENTS.get(self.task_id, {})
        services = [ServiceStatus(**svc.to_dict()) for svc in self.infrastructure.services.values()]
        
        return IncidentState(
            episode_id=self.episode_id,
            task_id=self.task_id,
            step_count=self.step_count,
            services=services,
            incident_resolved=self._check_incident_resolved(),
            diagnosis_submitted=self.diagnosis_submitted,
            actions_taken=self.actions_taken,
            cumulative_reward=self.cumulative_reward,
            # Ground truth is intentionally withheld from agent-visible state
            ground_truth_diagnosis="",
            ground_truth_fix="",
        )
    
    def _make_observation(self) -> IncidentObservation:
        """Create an observation from current state."""
        services = [ServiceStatus(**svc.to_dict()) for svc in self.infrastructure.services.values()]
        
        alert_message = "=== INCIDENT ALERT ===\n"
        for svc in services:
            if svc.status != "healthy":
                alert_message += f"Severity: HIGH\nAlert: {'High error rate' if svc.error_rate_percent > 50 else 'Degraded service'} on {svc.name} ({svc.error_rate_percent:.1f}% errors)\n"
        
        return IncidentObservation(
            alert_message=alert_message or "No active alerts",
            system_dashboard=services,
            last_action_result=self.last_action_result,
            steps_taken=self.step_count,
            max_steps=self.max_steps,
            sla_remaining_minutes=self.sla_remaining_minutes,
        )
    
    def _calculate_reward(self, action: IncidentAction) -> Tuple[float, Dict]:
        """Calculate reward for an action."""
        reward = 0.0
        breakdown = {}
        
        # 1. Investigation quality
        investigation_reward = 0.0
        if action.action_type == "investigate":
            if action.target in self.infrastructure.affected_services:
                investigation_reward = 0.05
            else:
                investigation_reward = -0.02
        breakdown["investigation"] = investigation_reward
        reward += investigation_reward

        # Encourage broad but purposeful investigation coverage.
        exploration_reward = 0.0
        if action.action_type == "investigate" and action.target not in self.investigated_targets:
            exploration_reward = 0.02
            self.investigated_targets.add(action.target)
        breakdown["exploration"] = exploration_reward
        reward += exploration_reward
        
        # 2. Diagnosis accuracy
        diagnosis_reward = 0.0
        if action.action_type == "diagnose" and action.command == "submit_diagnosis":
            # Require at least 2 investigation actions before diagnosis is credited
            investigation_count = len(self.investigated_targets)
            if investigation_count < 2:
                diagnosis_reward = -0.15  # Premature diagnosis penalty
                self.diagnosis_submitted = action.params.get("root_cause", "")
            else:
                self.diagnosis_submitted = action.params.get("root_cause", "")
                incident_config = INCIDENTS.get(self.task_id, {})
                ground_truth = incident_config.get("ground_truth_diagnosis", "")
                
                if self.diagnosis_submitted.lower() == ground_truth.lower():
                    diagnosis_reward = 0.25
                    self.correct_diagnosis = True
                else:
                    diagnosis_reward = -0.10
        breakdown["diagnosis"] = diagnosis_reward
        reward += diagnosis_reward
        
        # 3. Remediation effectiveness
        remediation_reward = 0.0
        if action.action_type == "remediate":
            # Check if action reduced errors significantly
            services = self.infrastructure.services
            has_healthy = any(s.status == "healthy" for s in services.values())
            has_degraded = any(s.status == "degraded" for s in services.values())
            
            if not has_degraded and has_healthy:
                # Made progress towards resolution
                remediation_reward = 0.15
            else:
                remediation_reward = 0.0

            if "no significant state change" in self.last_action_result.lower() or "immediately degraded again" in self.last_action_result.lower() or "partial recovery" in self.last_action_result.lower():
                self.failed_remediations += 1
        breakdown["remediation"] = remediation_reward
        reward += remediation_reward

        # Penalize risky remediation patterns that game the environment.
        safety_penalty = 0.0
        # Penalty for remediating services that are NOT the root cause
        root_cause = INCIDENTS.get(self.task_id, {}).get("root_cause_service", "")
        if action.action_type == "remediate" and action.target != root_cause:
            safety_penalty -= 0.15  # Non-root-cause remediation penalty

        if action.command == "restart":
            self.restart_targets.add(action.target)

        # Trigger shotgun penalty at 2 restarts (was 3)
        if len(self.restart_targets) >= 2 and not self.shotgun_penalty_applied:
            safety_penalty -= 0.50
            self.shotgun_penalty_applied = True

        if self.failed_remediations >= 2:
            safety_penalty -= 0.08

        breakdown["safety_penalty"] = safety_penalty
        reward += safety_penalty
        
        # 4. Time pressure penalty
        time_penalty = -0.02
        breakdown["time_penalty"] = time_penalty
        reward += time_penalty
        
        # 5. Bonus for resolving incident
        if self._check_incident_resolved():
            resolve_bonus = 0.50
            breakdown["resolution_bonus"] = resolve_bonus
            reward += resolve_bonus
        
        # Clamp reward
        reward = max(-1.0, min(1.0, reward))
        
        return reward, breakdown
    
    def _check_incident_resolved(self) -> bool:
        """Check if all services are healthy."""
        services = self.infrastructure.services
        return all(s.status == "healthy" for s in services.values())
