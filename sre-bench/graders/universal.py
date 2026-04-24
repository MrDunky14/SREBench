"""Universal grader for SREBench tasks.

Works for any task by pulling ground truth from INCIDENTS dict.
Grading criteria:
- Correct diagnosis? (0.30 points)
- System recovered? (0.30 points)
- Investigation before remediation? (0.15 points)
- No collateral damage? (0.10 points)
- Efficiency bonus (0.15 max)
- Anti-exploit penalties
"""
from src.environment import INCIDENTS


def grade_universal(env) -> float:
    """Grade any SREBench task using the INCIDENTS config.

    Args:
        env: SREBenchEnvironment instance

    Returns:
        Score in [0.0, 1.0]
    """
    final_state = env.state()
    score = 0.0

    incident = INCIDENTS.get(env.task_id, {})
    ground_truth = incident.get("ground_truth_diagnosis", "")

    # 1. Diagnosis accuracy (0.30)
    submitted = final_state.diagnosis_submitted
    if submitted and ground_truth:
        if submitted.lower() == ground_truth.lower():
            score += 0.30
        else:
            # Partial credit for mentioning key terms
            gt_tokens = set(ground_truth.lower().replace("_", " ").split())
            sub_tokens = set(submitted.lower().replace("_", " ").split())
            overlap = gt_tokens & sub_tokens
            if len(overlap) >= 1:
                score += 0.10

    # 2. System recovery (0.30)
    all_healthy = all(s.status == "healthy" for s in final_state.services)
    root_svc = incident.get("root_cause_service", "")
    root_recovered = any(
        s.name == root_svc and s.status == "healthy" for s in final_state.services
    )

    if all_healthy:
        score += 0.30
    elif root_recovered:
        score += 0.10

    # 3. Investigation quality (0.15)
    investigation_count = len(env.investigated_targets)
    if investigation_count >= 2:
        score += 0.15
    elif investigation_count == 1:
        score += 0.05

    # 4. No collateral damage (0.10)
    unnecessary_restarts = sum(
        1 for action in final_state.actions_taken
        if "restart" in action and root_svc not in action
    )
    if unnecessary_restarts == 0:
        score += 0.10

    # 5. Anti-exploit: penalize shotgun restarts
    if env.shotgun_penalty_applied:
        score -= 0.25

    # Penalize no diagnosis submitted
    if env.diagnosis_submitted is None:
        score -= 0.10

    # 6. Efficiency (0.15)
    cached_solution = env.solution_cache.get(env.task_id)
    if cached_solution:
        optimal_steps = cached_solution["steps"]
        actual_steps = final_state.step_count
        if actual_steps <= optimal_steps:
            score += 0.15
        else:
            extra_steps = actual_steps - optimal_steps
            score -= min(extra_steps * 0.01, 0.15)
    else:
        if final_state.step_count <= 8:
            score += 0.10
        elif final_state.step_count <= 12:
            score += 0.05

    return min(max(score, 0.001), 0.999)
