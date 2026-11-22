"""
Comprehensive Pytest Suite for SREBench.
Tests:
1. All 12 tasks + compound random task lifecycle (initialize, step, grade).
2. Log formatting: zero unformatted '{' or '}' braces across all 12 fault types in INCIDENTS.
3. Anti-exploit guards:
   a) Shotgun restart penalty when >= 2 distinct services restarted (-0.50).
   b) Premature diagnosis penalty when < 2 distinct targets investigated (-0.15).
   c) Non-root remediation penalty (-0.15).
   d) Ground truth hidden in state().
4. Root models.py and client.py functions.
5. FastAPI server endpoints via TestClient (/tasks, /reset, /step, /state, /grader, /observation_space, /action_space).
"""

import sys
from pathlib import Path
import pytest

# Ensure root and sre-bench are on sys.path
root_dir = Path(__file__).resolve().parent.parent
sre_bench_dir = root_dir / "sre-bench"
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(sre_bench_dir) not in sys.path:
    sys.path.insert(0, str(sre_bench_dir))

from src.environment import SREBenchEnvironment, INCIDENTS
from src.infrastructure import Infrastructure, LOG_TEMPLATES
from src.models import (
    IncidentAction,
    IncidentObservation,
    IncidentReward,
    IncidentState,
    ServiceStatus,
    ActionSchema,
)
from src.server import app, GRADERS
from fastapi.testclient import TestClient


# ==============================================================================
# 1. All 12 Tasks + Random Compound Task Lifecycle
# ==============================================================================

@pytest.mark.parametrize("task_id", list(INCIDENTS.keys()))
def test_all_12_tasks_lifecycle(task_id):
    """Verify each of the 12 standard tasks initializes, steps, and grades cleanly."""
    env = SREBenchEnvironment()
    obs = env.reset(task_id)
    assert isinstance(obs, IncidentObservation)
    assert obs.alert_message != ""
    assert len(obs.system_dashboard) == 6

    # Take an investigation step
    action = IncidentAction(
        action_type="investigate",
        command="check_logs",
        target="api-gateway",
        params={},
    )
    obs, reward, done, info = env.step(action)
    assert isinstance(obs, IncidentObservation)
    assert isinstance(reward, IncidentReward)
    assert isinstance(done, bool)

    # Verify grader runs cleanly
    grader_fn = GRADERS.get(task_id)
    assert grader_fn is not None
    score = grader_fn(env)
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_random_compound_task_lifecycle():
    """Verify procedural random / compound task initializes, steps, and grades cleanly."""
    env = SREBenchEnvironment()
    obs = env.reset("random")
    assert isinstance(obs, IncidentObservation)
    assert len(obs.system_dashboard) == 6

    # Take a step
    action = {"action_type": "investigate", "command": "check_metrics", "target": "database-primary", "params": {}}
    obs, reward, done, info = env.step(action)
    assert isinstance(obs, IncidentObservation)
    assert isinstance(reward, IncidentReward)

    # Universal grader routes cleanly for random
    from graders.universal import grade_universal
    score = grade_universal(env)
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


# ==============================================================================
# 2. Log Formatting: Zero Unformatted Placeholder Braces
# ==============================================================================

def test_log_formatting_no_unformatted_braces():
    """
    Assert that across all fault types in LOG_TEMPLATES and INCIDENTS,
    no generated log message contains unformatted '{' or '}' braces.
    """
    infra = Infrastructure(seed=12345)
    all_fault_types = set(LOG_TEMPLATES.keys())
    for task_cfg in INCIDENTS.values():
        all_fault_types.add(task_cfg["fault_type"])

    services = ["api-gateway", "user-service", "payment-service", "database-primary", "database-replica", "cache-redis"]

    for fault in all_fault_types:
        for svc_name in services:
            infra._gen_logs(svc_name, fault)
            svc = infra.services[svc_name]
            for log_entry in svc.log_buffer:
                msg = log_entry.message
                assert "{" not in msg and "}" not in msg, (
                    f"Unformatted template placeholder found in fault '{fault}' for service '{svc_name}': {msg}"
                )


# ==============================================================================
# 3. Anti-Exploit Guards
# ==============================================================================

def test_anti_exploit_shotgun_restart_penalty():
    """Verify shotgun penalty (-0.50) is triggered when >= 2 distinct services are restarted."""
    env = SREBenchEnvironment()
    env.reset("easy_restart")

    # Restart service 1: user-service
    act1 = IncidentAction(action_type="remediate", command="restart", target="user-service", params={})
    _, rew1, _, _ = env.step(act1)
    assert env.shotgun_penalty_applied is False

    # Restart service 2: payment-service (triggers 2nd distinct service restart)
    act2 = IncidentAction(action_type="remediate", command="restart", target="payment-service", params={})
    _, rew2, _, _ = env.step(act2)
    assert env.shotgun_penalty_applied is True
    assert rew2.breakdown.get("safety_penalty", 0.0) <= -0.50


def test_anti_exploit_premature_diagnosis_penalty():
    """Verify premature diagnosis penalty (-0.15) is applied when < 2 distinct targets investigated."""
    env = SREBenchEnvironment()
    env.reset("easy_restart")

    # Only 1 service investigated
    act1 = IncidentAction(action_type="investigate", command="check_logs", target="payment-service", params={})
    env.step(act1)
    assert len(env.investigated_targets) == 1

    # Diagnosis submitted prematurely
    act2 = IncidentAction(
        action_type="diagnose",
        command="submit_diagnosis",
        target="payment-service",
        params={"root_cause": "oom_killed"},
    )
    _, rew2, _, _ = env.step(act2)
    assert rew2.breakdown.get("diagnosis", 0.0) == -0.15
    assert env.correct_diagnosis is False


def test_anti_exploit_non_root_remediation_penalty():
    """Verify non-root remediation penalty (-0.15) is applied when remediating an unaffected/non-root service."""
    env = SREBenchEnvironment()
    env.reset("easy_restart")  # Root cause is payment-service

    # Remediate non-root service: api-gateway
    act = IncidentAction(action_type="remediate", command="scale_up", target="api-gateway", params={})
    _, rew, _, _ = env.step(act)
    assert rew.breakdown.get("safety_penalty", 0.0) == -0.15


def test_anti_exploit_ground_truth_hidden_in_state():
    """Verify ground truth diagnosis and fix are empty in agent-visible state."""
    env = SREBenchEnvironment()
    env.reset("easy_restart")
    st = env.state()
    assert isinstance(st, IncidentState)
    assert st.ground_truth_diagnosis == ""
    assert st.ground_truth_fix == ""


# ==============================================================================
# 4. Root models.py and client.py
# ==============================================================================

def test_root_models_export():
    """Verify root models.py cleanly exports all required OpenEnv models."""
    import models
    assert hasattr(models, "ServiceStatus")
    assert hasattr(models, "IncidentAction")
    assert hasattr(models, "IncidentObservation")
    assert hasattr(models, "IncidentReward")
    assert hasattr(models, "IncidentState")
    assert hasattr(models, "ActionSchema")

    # Verify instantiation
    action = models.IncidentAction(action_type="investigate", command="check_logs", target="api-gateway")
    assert action.target == "api-gateway"


def test_root_client_functions():
    """Verify root client.py provides working OpenEnv client interface."""
    import client

    # Reset
    obs = client.reset("easy_restart")
    assert obs is not None

    # Step with dict
    obs, rew, done, info = client.step({"action_type": "investigate", "command": "check_logs", "target": "payment-service", "params": {}})
    assert obs is not None
    assert rew is not None

    # Step with IncidentAction
    act = IncidentAction(action_type="investigate", command="check_metrics", target="api-gateway", params={})
    obs, rew, done, info = client.step(act)
    assert obs is not None

    # Helper getters
    tasks = client.get_tasks()
    if isinstance(tasks, dict):
        assert "tasks" in tasks
        assert len(tasks["tasks"]) >= 13
    else:
        assert isinstance(tasks, list)
        assert len(tasks) >= 13

    st = client.get_state()
    assert st is not None
    diag = st["ground_truth_diagnosis"] if isinstance(st, dict) else st.ground_truth_diagnosis
    assert diag == ""

    obs_space = client.get_observation_space()
    assert obs_space is not None

    act_space = client.get_action_space()
    assert act_space is not None


# ==============================================================================
# 5. FastAPI Endpoints via TestClient
# ==============================================================================

@pytest.fixture(scope="module")
def api_client():
    return TestClient(app)


def test_fastapi_endpoints(api_client):
    """Verify all FastAPI routes respond with valid 200 schemas."""
    # Health
    r = api_client.get("/")
    assert r.status_code == 200

    # Tasks
    r = api_client.get("/tasks")
    assert r.status_code == 200
    tasks_data = r.json()
    assert "tasks" in tasks_data
    assert len(tasks_data["tasks"]) >= 13

    # Reset with specific task
    r = api_client.post("/reset", json={"task_id": "easy_restart"})
    assert r.status_code == 200
    reset_data = r.json()
    assert "alert_message" in reset_data

    # Step
    step_payload = {
        "action_type": "investigate",
        "command": "check_logs",
        "target": "payment-service",
        "params": {},
    }
    r = api_client.post("/step", json=step_payload)
    assert r.status_code == 200
    step_data = r.json()
    assert "observation" in step_data
    assert "reward" in step_data

    # State (with withheld ground truth)
    r = api_client.get("/state")
    assert r.status_code == 200
    state_data = r.json()
    assert state_data["ground_truth_diagnosis"] == ""
    assert state_data["ground_truth_fix"] == ""

    # Grader
    r = api_client.get("/grader")
    assert r.status_code == 200
    grader_data = r.json()
    assert "score" in grader_data

    # Reset with random compound task
    r = api_client.post("/reset", json={"task_id": "random"})
    assert r.status_code == 200

    # Grader for random task
    r = api_client.get("/grader")
    assert r.status_code == 200

    # Observation space
    r = api_client.get("/observation_space")
    assert r.status_code == 200

    # Action space
    r = api_client.get("/action_space")
    assert r.status_code == 200


def test_gymnasium_rollout():
    """Verify Gymnasium wrapper environment rollout."""
    sys.path.insert(0, str(sre_bench_dir))
    from gymnasium_env import SREBenchGymEnv

    env = SREBenchGymEnv(task_id="easy_restart")
    obs, info = env.reset()
    assert obs.shape == (32,)
    assert isinstance(info, dict)

    # Execute a step using action space sample
    action = env.action_space.sample()
    next_obs, reward, terminated, truncated, step_info = env.step(action)
    assert next_obs.shape == (32,)
    assert isinstance(reward, float)
    assert isinstance(terminated, bool)
    assert isinstance(truncated, bool)

    # Test diagnosis action encoding
    # action 4 corresponds to submit_diagnosis
    action_obj = env._action_to_incident_action(16)
    assert action_obj.action_type in ["investigate", "diagnose", "remediate", "give_up"]

