"""FastAPI server for SREBench environment."""
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, Any
from .models import IncidentAction, IncidentObservation, IncidentReward, IncidentState
from .environment import SREBenchEnvironment, INCIDENTS
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from graders.easy import grade_easy
from graders.medium import grade_medium
from graders.hard import grade_hard

app = FastAPI(title="SREBench Environment")

# Global environment instance
env = SREBenchEnvironment()
episode_history = []

GRADERS = {
    "easy_restart": grade_easy,
    "medium_cascade": grade_medium,
    "hard_intermittent": grade_hard,
}


@app.get("/")
def health():
    """Health check endpoint."""
    return {"status": "ok", "message": "SREBench environment is running"}


@app.get("/tasks")
def get_tasks():
    """Get available tasks and action schema."""
    return {
        "tasks": [
            {
                "id": "easy_restart",
                "name": "Service Restart",
                "description": "Diagnose and restart a single OOMKilled service.",
                "difficulty": "easy",
            },
            {
                "id": "medium_cascade",
                "name": "Cascading Failure",
                "description": "Trace and fix a cascading failure across dependent services caused by a database bottleneck.",
                "difficulty": "medium",
            },
            {
                "id": "hard_intermittent",
                "name": "Intermittent Nightmare",
                "description": "Diagnose intermittent latency spikes caused by subtle cache fragmentation.",
                "difficulty": "hard",
            },
        ],
        "action_schema": IncidentAction.schema(),
    }


@app.post("/reset")
def reset_env(payload: Dict[str, Any]):
    """Reset environment for a new episode."""
    global episode_history
    task_id = payload.get("task_id", "easy_restart")
    
    if task_id not in INCIDENTS:
        raise HTTPException(status_code=400, detail=f"Unknown task: {task_id}")
    
    # Save previous episode to history
    if env.step_count > 0:
        episode_history.append({
            "episode_id": env.episode_id,
            "task_id": env.task_id,
            "steps": env.step_count,
            "cumulative_reward": env.cumulative_reward,
            "incident_resolved": env._check_incident_resolved() if env.infrastructure else False,
        })
    
    obs = env.reset(task_id)
    return obs.dict()


@app.post("/step")
def step_env(action: IncidentAction):
    """Take a step in the environment."""
    if not env.infrastructure:
        raise HTTPException(status_code=400, detail="Environment not initialized. Call /reset first.")
    
    obs, reward, done, info = env.step(action)
    
    return {
        "observation": obs.dict(),
        "reward": reward.dict(),
        "done": done,
        "info": info,
    }


@app.get("/state")
def get_state():
    """Get full internal state."""
    if not env.infrastructure:
        raise HTTPException(status_code=400, detail="Environment not initialized. Call /reset first.")
    
    state = env.state()
    return state.dict()


@app.get("/grader")
def grade_episode(task_id: str = None):
    """Grade the current episode."""
    if not env.infrastructure:
        raise HTTPException(status_code=400, detail="No episode in progress.")
    
    task_id = task_id or env.task_id
    
    if task_id not in GRADERS:
        raise HTTPException(status_code=400, detail=f"No grader for task: {task_id}")
    
    grader_fn = GRADERS[task_id]
    
    # Pass environment to grader so it can access solution_cache
    score = grader_fn(env)
    
    return {
        "task_id": task_id,
        "episode_id": env.episode_id,
        "score": score,
        "steps": env.step_count,
        "cumulative_reward": env.cumulative_reward,
        "incident_resolved": env._check_incident_resolved(),
        "diagnosis_submitted": env.diagnosis_submitted,
    }


@app.post("/baseline")
def run_baseline(payload: Dict[str, Any] = None):
    """Run a baseline episode using a simple strategy."""
    task_id = payload.get("task_id", "easy_restart") if payload else "easy_restart"
    
    obs_model = env.reset(task_id)
    obs = obs_model.dict()  # Convert Pydantic model to dict
    done = False
    step_count = 0
    
    actions_log = []
    
    # Simple baseline: check logs on degraded services, then attempt fixes
    while not done and step_count < 20:
        step_count += 1
        
        # Find degraded/down services
        degraded = [s for s in obs["system_dashboard"] if s["status"] != "healthy"]
        
        if not degraded:
            break
        
        # Strategy: check logs, then check metrics
        target = degraded[0]["name"]
        
        if step_count % 2 == 1:
            # Check logs
            action = IncidentAction(
                action_type="investigate",
                command="check_logs",
                target=target,
                params={"severity": "ERROR", "last_n": 20},
            )
        else:
            # Attempt fix based on error patterns
            if "memory" in obs.get("last_action_result", "").lower():
                action = IncidentAction(
                    action_type="remediate",
                    command="restart",
                    target=target,
                    params={},
                )
            elif "connection" in obs.get("last_action_result", "").lower():
                action = IncidentAction(
                    action_type="remediate",
                    command="increase_pool",
                    target="database-primary",
                    params={"new_max": 500},
                )
            elif "cache" in obs.get("last_action_result", "").lower():
                action = IncidentAction(
                    action_type="remediate",
                    command="flush_cache",
                    target="cache-redis",
                    params={},
                )
            else:
                action = IncidentAction(
                    action_type="investigate",
                    command="check_metrics",
                    target=target,
                    params={"metric": "cpu"},
                )
        
        result = step_env(action)
        obs = result["observation"]
        done = result["done"]
        actions_log.append({"action": action.dict(), "reward": result["reward"]["value"]})
    
    grade_result = grade_episode(task_id)
    
    return {
        "episode_id": env.episode_id,
        "task_id": task_id,
        "steps": step_count,
        "score": grade_result["score"],
        "actions": actions_log,
    }