"""Pydantic models for SREBench environment."""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Literal


class ServiceStatus(BaseModel):
    """Status of a single service in the system."""
    name: str
    status: Literal["healthy", "degraded", "down"]
    cpu_percent: float = Field(ge=0, le=100)
    memory_percent: float = Field(ge=0, le=100)
    error_rate_percent: float = Field(ge=0, le=100)
    latency_p99_ms: float = Field(ge=0)


class IncidentAction(BaseModel):
    """Agent action: investigate, diagnose, or remediate."""
    action_type: Literal["investigate", "diagnose", "remediate", "give_up"]
    command: str  # check_logs, check_metrics, check_connections, restart, scale_up, increase_pool, flush_cache, rollback, failover, submit_diagnosis
    target: str   # service name
    params: Dict = Field(default_factory=dict)


class IncidentObservation(BaseModel):
    """Observation returned to agent after each step."""
    alert_message: str
    system_dashboard: List[ServiceStatus]
    last_action_result: str
    steps_taken: int
    max_steps: int
    sla_remaining_minutes: float


class IncidentReward(BaseModel):
    """Reward signal with breakdown."""
    value: float = Field(ge=-1.0, le=1.0)
    breakdown: Dict[str, float] = Field(default_factory=dict)
    episode_id: str = ""


class IncidentState(BaseModel):
    """Full internal state of simulation."""
    episode_id: str
    task_id: str
    step_count: int
    services: List[ServiceStatus]
    incident_resolved: bool
    diagnosis_submitted: Optional[str] = None
    actions_taken: List[str]
    cumulative_reward: float
    ground_truth_diagnosis: str = ""
    ground_truth_fix: str = ""