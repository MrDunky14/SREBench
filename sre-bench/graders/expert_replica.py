"""Expert task grader: Database Replica Sync Failure.

Grading criteria:
- Did system recover? (0.35 points)
- Was correct remediation applied? (0.25 points)
- Investigation quality (0.15 points)
- Efficiency bonus (0.15 max)
- Anti-exploit penalties
"""
from src.environment import INCIDENTS


def grade_expert_replica(env) -> float:
    """Grade the expert database replica sync task.

    Args:
        env: SREBenchEnvironment instance

    Returns:
        Score in [0.0, 1.0]
    """
    final_state = env.state()
    score = 0.0

    # Check if system recovered
    all_healthy = all(s.status == "healthy" for s in final_state.services)
    if all_healthy:
        score += 0.35

    # Check if correct fix was applied
    if final_state.incident_resolved and "restart" in " ".join(final_state.actions_taken):
        score += 0.25

    # Investigation quality
    investigation_count = len(env.investigated_targets)
    if investigation_count >= 2:
        score += 0.15
    elif investigation_count == 1:
        score += 0.05

    # Anti-exploit
    if env.shotgun_penalty_applied:
        score -= 0.25

    # Efficiency comparison
    cached_solution = env.solution_cache.get(env.task_id)
    if cached_solution:
        optimal_steps = cached_solution['steps']
        actual_steps = final_state.step_count
        if actual_steps <= optimal_steps:
            score += 0.15
        else:
            extra_steps = actual_steps - optimal_steps
            score -= min(extra_steps * 0.01, 0.15)
    else:
        if final_state.step_count <= 5:
            score += 0.15
        elif final_state.step_count <= 8:
            score += 0.05

    return min(max(score, 0.001), 0.999)
