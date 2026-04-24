"""Medium task grader: Cascading Failure Diagnosis.

Grading criteria:
- Root cause identified? (0.30 points)
- System recovered? (0.30 points)
- Did agent investigate? (0.15 points)
- No collateral damage? (0.10 points)
- Efficiency bonus (0.15 max)
- Anti-exploit penalties
"""
from src.environment import INCIDENTS


def grade_medium(env) -> float:
    """Grade the medium task (cascading failure).

    Args:
        env: SREBenchEnvironment instance

    Returns:
        Score in [0.0, 1.0]
    """
    final_state = env.state()
    score = 0.0

    # Get ground truth from INCIDENTS (not from state, which is hidden from agents)
    incident = INCIDENTS.get(env.task_id, {})
    ground_truth = incident.get("ground_truth_diagnosis", "")

    # Check diagnosis accuracy
    submitted = final_state.diagnosis_submitted
    if submitted and ground_truth:
        if submitted.lower() == ground_truth.lower():
            score += 0.30
        elif any(keyword in submitted.lower() for keyword in ["connection", "pool", "database"]):
            score += 0.10  # Partial credit

    # Check system recovery
    all_healthy = all(s.status == "healthy" for s in final_state.services)
    primary_recovered = any(s.name == "database-primary" and s.status == "healthy" for s in final_state.services)

    if all_healthy:
        score += 0.30
    elif primary_recovered:
        score += 0.10

    # Investigation quality
    investigation_count = len(env.investigated_targets)
    if investigation_count >= 2:
        score += 0.15
    elif investigation_count == 1:
        score += 0.05

    # No collateral damage (unnecessary restarts)
    unnecessary_restarts = sum(
        1 for action in final_state.actions_taken
        if "restart" in action and "payment" in action
    )
    if unnecessary_restarts == 0:
        score += 0.10

    # Anti-exploit: penalize shotgun restarts
    if env.shotgun_penalty_applied:
        score -= 0.25

    # Efficiency
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
        if final_state.step_count <= 10:
            score += 0.10
        elif final_state.step_count <= 15:
            score += 0.05

    return min(max(score, 0.001), 0.999)
