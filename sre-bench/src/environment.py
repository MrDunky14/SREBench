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
        
        # Create new infrastructure and inject incident
        incident_config = INCIDENTS.get(task_id, INCIDENTS["easy_restart"])
        self.infrastructure = Infrastructure(seed=hash(self.episode_id) % (2**31))
        self.infrastructure.inject_incident(incident_config)
        
        # Generate initial observation
        self.last_action_result = f"Incident detected: {incident_config['description']}"
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
            ground_truth_diagnosis=incident_config.get("ground_truth_diagnosis", ""),
            ground_truth_fix=incident_config.get("ground_truth_fix", ""),
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
        
        # 2. Diagnosis accuracy
        diagnosis_reward = 0.0
        if action.action_type == "diagnose" and action.command == "submit_diagnosis":
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
        breakdown["remediation"] = remediation_reward
        reward += remediation_reward
        
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
