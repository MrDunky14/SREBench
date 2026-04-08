"""Medium task grader: Cascading Failure Diagnosis.

Grading criteria:
- Root cause identified? (0.35 points)
- System recovered? (0.35 points)
- No collateral damage? (0.15 points)
- Efficiency bonus based on solution cache:
  - Same steps as cached optimal: full efficiency credit
  - More steps: -0.01 per extra step (creates natural variance)
  - This ensures agents are incentivized to match or beat optimal path
"""


def grade_medium(env) -> float:
    """Grade the medium task (cascading failure).
    
    Args:
        env: SREBenchEnvironment instance with solution_cache and step_count
    
    Returns:
        Score in [0.0, 1.0]
    """
    final_state = env.state()
    score = 0.0
    
    # Check diagnosis accuracy
    ground_truth = final_state.ground_truth_diagnosis
    submitted = final_state.diagnosis_submitted
    
    if submitted and ground_truth:
        if submitted.lower() == ground_truth.lower():
            score += 0.35
        elif any(keyword in submitted.lower() for keyword in ["connection", "pool", "database"]):
            score += 0.15  # Partial credit for identifying database/connection issue
    
    # Check system recovery
    all_healthy = all(s.status == "healthy" for s in final_state.services)
    primary_recovered = any(s.name == "database-primary" and s.status == "healthy" for s in final_state.services)
    
    if all_healthy:
        score += 0.35
    elif primary_recovered:
        score += 0.15
    
    # No collateral damage (check if unnecessary restarts were done)
    unnecessary_restarts = sum(
        1 for action in final_state.actions_taken 
        if "restart" in action and "payment" in action
    )
    if unnecessary_restarts == 0:
        score += 0.15
    
    # Efficiency comparison: measure against cached optimal solution
    cached_solution = env.solution_cache.get(env.task_id)
    
    if cached_solution:
        # Cached solution exists: compare agent's steps to optimal
        optimal_steps = cached_solution['steps']
        actual_steps = final_state.step_count
        
        # Base efficiency bonus (0.15 for matching or beating cached optimal)
        if actual_steps <= optimal_steps:
            score += 0.15  # Agent matched or beat optimal
        else:
            # Penalty: -0.01 per extra step taken, capped at -0.15
            extra_steps = actual_steps - optimal_steps
            efficiency_penalty = min(extra_steps * 0.01, 0.15)
            score -= efficiency_penalty
    else:
        # No cached solution yet: give efficiency bonus based on absolute step count
        # This rewards the first agent that solves the task
        if final_state.step_count <= 10:
            score += 0.10
        elif final_state.step_count <= 15:
            score += 0.05
    
    return min(max(score, 0.001), 0.999)

