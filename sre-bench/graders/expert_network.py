"""Expert task grader: Network Partition Detection.

Grading criteria:
- Did system recover? (0.50 points)
- Was failover executed correctly? (0.30 points)
- Efficiency bonus based on solution cache:
  - Same steps as cached optimal: 0.20 points
  - More steps: -0.01 per extra step (up to -0.15)
"""


def grade_expert_network(env) -> float:
    """Grade the expert network partition task.
    
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
    
    # Check if failover was correctly diagnosed and executed
    if final_state.incident_resolved and "failover" in " ".join(final_state.actions_taken):
        score += 0.30
    
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
            score += 0.15
        elif final_state.step_count <= 8:
            score += 0.05
    
    return min(max(score, 0.0), 1.0)
