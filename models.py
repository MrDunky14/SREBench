"""Models and schemas for SREBench - exported at root level for OpenEnv."""

import sys
from pathlib import Path

# Add sre-bench to Python path
sre_bench_path = Path(__file__).resolve().parent / "sre-bench"
if str(sre_bench_path) not in sys.path:
    sys.path.insert(0, str(sre_bench_path))

# Import all models from src for OpenEnv compatibility
from src.models import (
    ServiceStatus,
    IncidentAction,
    IncidentObservation,
    IncidentReward,
    IncidentState,
    ActionSchema,
)

__all__ = [
    "ServiceStatus",
    "IncidentAction",
    "IncidentObservation",
    "IncidentReward",
    "IncidentState",
    "ActionSchema",
]
