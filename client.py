"""OpenEnv client for SREBench environment."""

import sys
from pathlib import Path

# Add sre-bench to Python path
sys.path.insert(0, str(Path(__file__).parent / "sre-bench"))

from src.environment import SREBenchEnvironment

# Create a single instance of the environment for OpenEnv
env = SREBenchEnvironment()


def reset(task_id: str = None):
    """Reset the environment for a specific task."""
    return env.reset(task_id=task_id)


def step(action: dict):
    """Execute an action in the environment."""
    return env.step(action)


def get_tasks():
    """Get available tasks in the environment."""
    return env.get_tasks()


def get_state():
    """Get the current state of the environment."""
    return env.get_state()


def get_observation_space():
    """Get the observation space specification."""
    return env.get_observation_space()


def get_action_space():
    """Get the action space specification."""
    return env.get_action_space()
