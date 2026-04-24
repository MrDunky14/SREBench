"""Hard task grader: Intermittent Nightmare (Cache Fragmentation).

Grading criteria:
- Root cause identified? (0.30 points)
- System recovered? (0.30 points)
- Investigation quality (0.15 points)
- No collateral damage (0.10 points)
- Efficiency bonus (0.15 max)
- Anti-exploit penalties
"""
from src.environment import INCIDENTS


def grade_hard(env) -> float:
    """Grade the hard task (cache fragmentation).

    Args:
        env: SREBenchEnvironment instance

    Returns:
        Score in [0.0, 1.0]
    """
    final_state = env.state()
    score = 0.0

    # Get ground truth from INCIDENTS
    incident = INCIDENTS.get(env.task_id, {})
    ground_truth = incident.get("ground_truth_diagnosis", "")

    # Check diagnosis accuracy
    submitted = final_state.diagnosis_submitted
    if submitted and ground_truth:
        if submitted.lower() == ground_truth.lower():
            score += 0.30
        elif any(kw in submitted.lower() for kw in ["cache", "fragmentation", "eviction", "redis"]):
            score += 0.10

    # Check system recovery
    all_healthy = all(s.status == "healthy" for s in final_state.services)
    if all_healthy:
        score += 0.30

    # Investigation quality
    investigation_count = len(env.investigated_targets)
    if investigation_count >= 3:
        score += 0.15  # Hard task needs deeper investigation
    elif investigation_count >= 2:
        score += 0.10
    elif investigation_count == 1:
        score += 0.03

    # No collateral damage
    unnecessary_restarts = sum(
        1 for action in final_state.actions_taken
        if "restart" in action and any(svc in action for svc in ["payment", "user", "api-gateway"])
    )
    if unnecessary_restarts <= 1:
        score += 0.10

    # Anti-exploit
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
