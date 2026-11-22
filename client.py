"""OpenEnv client for SREBench environment."""

import sys
from pathlib import Path
from typing import Union, Dict, Any

# Add sre-bench to Python path
sre_bench_path = Path(__file__).resolve().parent / "sre-bench"
if str(sre_bench_path) not in sys.path:
    sys.path.insert(0, str(sre_bench_path))

from src.environment import SREBenchEnvironment, INCIDENTS
from src.models import IncidentAction

# Create a single instance of the environment for OpenEnv
env = SREBenchEnvironment()


def reset(task_id: str = None):
    """Reset the environment for a specific task."""
    if task_id is None:
        return env.reset()
    return env.reset(task_id=task_id)


def step(action: Union[dict, IncidentAction]):
    """Execute an action in the environment."""
    if isinstance(action, dict):
        action = IncidentAction(**action)
    return env.step(action)


def get_tasks():
    """Get available tasks in the environment."""
    if hasattr(env, "get_tasks"):
        return env.get_tasks()
    return [
        {"id": tid, "name": cfg.get("description", tid), "difficulty": tid.split("_")[0],
         "description": cfg.get("description", "")}
        for tid, cfg in INCIDENTS.items()
    ] + [
        {"id": "random", "name": "Random Incident",
         "description": "Procedurally generated — a random fault is selected each episode.",
         "difficulty": "random"}
    ]


def get_state():
    """Get the current state of the environment."""
    if hasattr(env, "get_state"):
        return env.get_state()
    if env.infrastructure is None:
        env.reset()
    return env.state()


def get_observation_space():
    """Get the observation space specification."""
    if hasattr(env, "get_observation_space"):
        return env.get_observation_space()
    return {
        "type": "IncidentObservation",
        "fields": ["alert_message", "system_dashboard", "last_action_result", "steps_taken", "max_steps", "sla_remaining_minutes"]
    }


def get_action_space():
    """Get the action space specification."""
    if hasattr(env, "get_action_space"):
        return env.get_action_space()
    if hasattr(IncidentAction, "model_json_schema"):
        return IncidentAction.model_json_schema()
    return IncidentAction.schema()
