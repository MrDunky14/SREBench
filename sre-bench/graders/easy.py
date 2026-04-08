"""Easy task grader: Service Restart.

Grading criteria:
- Did system recover? (0.50 points)
- Was correct remediation applied? (0.30 points)
- Efficiency bonus based on solution cache:
  - Same steps as cached optimal: no penalty
  - More steps: -0.01 per extra step (up to -0.15)
  - This creates NATURAL variance: agents that investigate too much pay efficiency cost
"""


def grade_easy(env) -> float:
    """Grade the easy task (service restart).
    
    Args:
        env: SREBenchEnvironment instance with solution_cache and step_count
    
    Returns:
        Score in [0.0, 1.0]
    """
    final_state = env.state()
    score = 0.0
    
    # Check if system recovered (all services healthy)
    all_healthy = all(s.status == "healthy" for s in final_state.services)
    if all_healthy:
        score += 0.50
    
    # Check if correct fix was applied (incident was resolved)
    if final_state.incident_resolved:
        score += 0.30
    
    # Efficiency comparison: measure against cached optimal solution
    cached_solution = env.solution_cache.get(env.task_id)
    
    if cached_solution:
        # Cached solution exists: compare agent's steps to optimal
        optimal_steps = cached_solution['steps']
        actual_steps = final_state.step_count
        
        # Base efficiency bonus (0.20 for matching or beating cached optimal)
        if actual_steps <= optimal_steps:
            score += 0.20  # Agent matched or beat optimal
        else:
            # Penalty: -0.01 per extra step taken, capped at -0.15
            extra_steps = actual_steps - optimal_steps
            efficiency_penalty = min(extra_steps * 0.01, 0.15)
            score -= efficiency_penalty
    else:
        # No cached solution yet: give efficiency bonus based on absolute step count
        # This rewards the first agent that solves the task
        if final_state.step_count <= 3:
            score += 0.15
        elif final_state.step_count <= 5:
            score += 0.05
    
    return min(max(score, 0.001), 0.999)

