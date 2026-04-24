"""Easy task grader: Service Restart.

Grading criteria:
- Did system recover? (0.40 points)
- Was correct remediation applied? (0.25 points)
- Did agent investigate before acting? (0.15 points)
- Efficiency bonus (0.20 max)
- Anti-exploit: penalize shotgun restarts and no-investigation strategies
"""


def grade_easy(env) -> float:
    """Grade the easy task (service restart).

    Args:
        env: SREBenchEnvironment instance

    Returns:
        Score in [0.0, 1.0]
    """
    final_state = env.state()
    score = 0.0

    # Check if system recovered (all services healthy)
    all_healthy = all(s.status == "healthy" for s in final_state.services)
    if all_healthy:
        score += 0.40

    # Check if correct fix was applied (incident was resolved)
    if final_state.incident_resolved:
        score += 0.25

    # Investigation quality: agent should have investigated before remediating
    investigation_count = len(env.investigated_targets)
    if investigation_count >= 2:
        score += 0.15  # Good: investigated at least 2 services
    elif investigation_count == 1:
        score += 0.05  # Partial credit
    # else: 0 — no investigation before acting

    # Anti-exploit: penalize shotgun restarts
    if env.shotgun_penalty_applied:
        score -= 0.35  # Heavy penalty for indiscriminate restarts

    # Penalize if no diagnosis was submitted
    if env.diagnosis_submitted is None:
        score -= 0.10

    # Efficiency comparison
    cached_solution = env.solution_cache.get(env.task_id)
    if cached_solution:
        optimal_steps = cached_solution['steps']
        actual_steps = final_state.step_count
        if actual_steps <= optimal_steps:
            score += 0.20
        else:
            extra_steps = actual_steps - optimal_steps
            efficiency_penalty = min(extra_steps * 0.01, 0.15)
            score -= efficiency_penalty
    else:
        if final_state.step_count <= 5:
            score += 0.10
        elif final_state.step_count <= 8:
            score += 0.05

    return min(max(score, 0.001), 0.999)
