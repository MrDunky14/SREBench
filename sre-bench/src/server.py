"""FastAPI server for SREBench environment."""
from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from typing import Dict, Any, List, Optional
from .models import IncidentAction, IncidentObservation, IncidentReward, IncidentState
from .environment import SREBenchEnvironment, INCIDENTS
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from graders.easy import grade_easy
from graders.medium import grade_medium
from graders.hard import grade_hard
from graders.expert_network import grade_expert_network
from graders.expert_replica import grade_expert_replica

app = FastAPI(title="SREBench Environment")

# Global environment instance
env = SREBenchEnvironment()
episode_history = []
leaderboard = {}  # {task_id: [{"agent_name": "", "score": 0.0, "steps": 0, "timestamp": ""}, ...]}

GRADERS = {
    "easy_restart": grade_easy,
    "medium_cascade": grade_medium,
    "hard_intermittent": grade_hard,
    "expert_network_partition": grade_expert_network,
    "expert_database_replica_sync": grade_expert_replica,
}


# Mount static files (UI)
static_dir = Path(__file__).parent.parent
if (static_dir / "index.html").exists():
    app.mount("/ui", StaticFiles(directory=str(static_dir), html=True), name="static")


@app.get("/")
def health():
    """Health check endpoint."""
    return {"status": "ok", "message": "SREBench environment is running"}


@app.get("/dashboard.html")
def dashboard():
    """Serve the interactive dashboard."""
    dashboard_path = Path(__file__).parent.parent / "dashboard.html"
    if dashboard_path.exists():
        return FileResponse(str(dashboard_path), media_type="text/html")
    raise HTTPException(status_code=404, detail="Dashboard not found")


@app.get("/war_room.html")
def war_room():
    """Serve the war-room style demo dashboard."""
    war_room_path = Path(__file__).parent.parent / "war_room.html"
    if war_room_path.exists():
        return FileResponse(str(war_room_path), media_type="text/html")
    raise HTTPException(status_code=404, detail="War room dashboard not found")


@app.get("/index.html")
def home():
    """Serve the home page."""
    index_path = Path(__file__).parent.parent / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path), media_type="text/html")
    raise HTTPException(status_code=404, detail="Home page not found")


@app.get("/docs-api")
def api_docs():
    """API documentation endpoint."""
    return {
        "title": "SREBench API Documentation",
        "description": "OpenEnv-compliant environment for SRE incident response training",
        "version": "1.0.0",
        "endpoints": {
            "GET /": "Health check",
            "GET /tasks": "List available incident scenarios",
            "POST /reset": "Initialize a new episode",
            "POST /step": "Execute an action in the environment",
            "GET /state": "Get full internal state",
            "GET /grader": "Grade the current episode",
            "GET /leaderboard": "View test leaderboards",
            "POST /baseline": "Run baseline agent strategy",
            "GET /dashboard.html": "Interactive testing dashboard",
            "GET /war_room.html": "War-room demo dashboard",
        },
    }


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
            {
                "id": "expert_network_partition",
                "name": "Network Partition Crisis",
                "description": "Detect and handle network partition between primary and replica databases.",
                "difficulty": "expert",
            },
            {
                "id": "expert_database_replica_sync",
                "name": "Database Sync Failure",
                "description": "Fix database replica sync failure caused by WAL synchronization issues.",
                "difficulty": "expert",
            },
        ],
        "action_schema": IncidentAction.schema(),
    }


@app.post("/reset")
def reset_env(payload: Optional[Dict[str, Any]] = Body(default=None)):
    """Reset environment for a new episode."""
    global episode_history
    task_id = payload.get("task_id", "easy_restart") if payload else "easy_restart"
    
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
    
    try:
        obs, reward, done, info = env.step(action)
        
        return {
            "observation": obs.dict(),
            "reward": reward.dict(),
            "done": done,
            "info": info,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Step execution failed: {str(e)}")


@app.get("/state")
def get_state():
    """Get agent-visible state (ground truth withheld to prevent reward hacking)."""
    if not env.infrastructure:
        raise HTTPException(status_code=400, detail="Environment not initialized. Call /reset first.")
    
    state = env.state()
    # Ground truth is intentionally empty in the state returned to agents
    return state.dict()


@app.get("/grader")
def grade_episode(task_id: str = None, agent_name: str = "anonymous"):
    """Grade the current episode."""
    if not env.infrastructure:
        raise HTTPException(status_code=400, detail="No episode in progress.")
    
    task_id = task_id or env.task_id
    
    if task_id not in GRADERS:
        raise HTTPException(status_code=400, detail=f"No grader for task: {task_id}")
    
    try:
        grader_fn = GRADERS[task_id]
        
        # Pass environment to grader so it can access solution_cache
        score = grader_fn(env)
        
        # Add to leaderboard
        if task_id not in leaderboard:
            leaderboard[task_id] = []
        
        leaderboard[task_id].append({
            "agent_name": agent_name,
            "score": score,
            "steps": env.step_count,
            "episode_id": env.episode_id,
            "timestamp": str(__import__('datetime').datetime.now().isoformat()),
        })
        
        # Sort leaderboard by score descending
        leaderboard[task_id].sort(key=lambda x: x["score"], reverse=True)
        
        return {
            "task_id": task_id,
            "episode_id": env.episode_id,
            "score": score,
            "steps": env.step_count,
            "cumulative_reward": env.cumulative_reward,
            "incident_resolved": env._check_incident_resolved(),
            "diagnosis_submitted": env.diagnosis_submitted,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Grading failed: {str(e)}")


@app.get("/leaderboard")
def get_leaderboard(task_id: str = None):
    """Get leaderboard for a specific task or all tasks."""
    if task_id:
        if task_id not in leaderboard:
            return {"task_id": task_id, "entries": []}
        return {
            "task_id": task_id,
            "entries": leaderboard[task_id][:10],  # Top 10
        }
    
    # Return all leaderboards
    result = {}
    for tid in INCIDENTS.keys():
        result[tid] = leaderboard.get(tid, [])[:10]
    
    return {"leaderboards": result}


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