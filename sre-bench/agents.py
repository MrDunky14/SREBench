"""
Baseline agents for SREBench.
Demonstrates different strategies for incident resolution.
"""

import random
import sys
from pathlib import Path
from typing import List, Tuple

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.models import IncidentAction, ServiceStatus


class RandomAgent:
    """Takes random actions. Baseline for comparison."""
    
    def __init__(self, env):
        self.env = env
        self.actions_taken = []
    
    def act(self, observation) -> IncidentAction:
        """Return random action."""
        action_types = ["investigate", "diagnose", "remediate", "give_up"]
        commands = [
            "check_logs", "check_metrics", "check_connections",
            "restart", "scale_up", "increase_pool", "flush_cache", "failover"
        ]
        targets = [
            "api-gateway", "user-service", "payment-service",
            "database-primary", "database-replica", "cache-redis"
        ]
        
        action = IncidentAction(
            action_type=random.choice(action_types),
            command=random.choice(commands),
            target=random.choice(targets),
            params={}
        )
        
        self.actions_taken.append(action)
        return action


class RuleBasedAgent:
    """
    Rule-based agent using heuristics.
    Strategy:
    1. Investigate all degraded services
    2. Check logs for error patterns
    3. Apply targeted fixes based on patterns
    """
    
    def __init__(self, env):
        self.env = env
        self.actions_taken = []
        self.investigated = set()
        self.diagnosis_submitted = False
    
    def act(self, observation) -> IncidentAction:
        """Execute rule-based action."""
        
        # Find degraded services
        degraded = [s for s in observation.system_dashboard if s.status != "healthy"]
        
        # Phase 1: Investigate
        if not self.investigated and degraded:
            target = degraded[0]
            self.investigated.add(target.name)
            
            # Choose investigation based on metrics
            if target.memory_percent > 80:
                cmd = "check_metrics"
            elif target.error_rate_percent > 50:
                cmd = "check_logs"
            else:
                cmd = "check_connections"
            
            action = IncidentAction(
                action_type="investigate",
                command=cmd,
                target=target.name,
                params={"severity": "ERROR"}
            )
        
        # Phase 2: Diagnosis
        elif not self.diagnosis_submitted and len(self.investigated) >= 2:
            # Infer diagnosis from patterns
            if degraded and degraded[0].memory_percent > 90:
                diagnosis = "oom_killed"
            elif degraded and degraded[0].error_rate_percent > 80:
                diagnosis = "connection_pool_exhaustion"
            else:
                diagnosis = "cache_fragmentation"
            
            action = IncidentAction(
                action_type="diagnose",
                command="submit_diagnosis",
                target=degraded[0].name if degraded else "unknown",
                params={"root_cause": diagnosis}
            )
            self.diagnosis_submitted = True
        
        # Phase 3: Remediation
        elif degraded:
            target = degraded[0]
            
            # Choose fix based on diagnosis pattern
            if target.memory_percent > 90:
                cmd = "restart"
            elif "database" in target.name and target.error_rate_percent > 80:
                cmd = "increase_pool"
            elif "cache" in target.name:
                cmd = "flush_cache"
            else:
                cmd = "restart"
            
            action = IncidentAction(
                action_type="remediate",
                command=cmd,
                target=target.name,
                params={}
            )
        
        # Phase 4: Give up
        else:
            action = IncidentAction(
                action_type="give_up",
                command="",
                target="",
                params={}
            )
        
        self.actions_taken.append(action)
        return action


class ReinforcementLearningPlaceholder:
    """
    Placeholder for RL agents trained with PPO, A2C, etc.
    
    Usage with standard RL frameworks:
    
    ```python
    from stable_baselines3 import PPO
    from sre_bench.gymnasium_env import SREBenchGymEnv
    
    # Create environment
    env = SREBenchGymEnv(task_id="easy_restart")
    
    # Train agent
    agent = PPO("MlpPolicy", env, verbose=1)
    agent.learn(total_timesteps=100000)
    
    # Evaluate
    obs, _ = env.reset()
    for _ in range(100):
        action, _ = agent.predict(obs)
        obs, reward, terminated, truncated, _ = env.step(action)
        if terminated or truncated:
            break
    ```
    """
    pass


class CurriculumLearningAgent:
    """
    Tracks performance across tasks and adapts strategy.
    Learns from previous episodes to improve on harder scenarios.
    """
    
    def __init__(self):
        self.performance = {}  # {task_id: [scores]}
        self.strategy = {}     # {task_id: best_strategy}
    
    def record_episode(self, task_id: str, score: float, actions: List[IncidentAction]):
        """Record episode results."""
        if task_id not in self.performance:
            self.performance[task_id] = []
            self.strategy[task_id] = []
        
        self.performance[task_id].append(score)
        self.strategy[task_id] = actions
    
    def get_statistics(self, task_id: str) -> dict:
        """Get performance stats for a task."""
        if task_id not in self.performance:
            return {}
        
        scores = self.performance[task_id]
        return {
            "task_id": task_id,
            "episodes": len(scores),
            "avg_score": sum(scores) / len(scores),
            "best_score": max(scores),
            "worst_score": min(scores),
            "improvement": scores[-1] - scores[0] if len(scores) > 1 else 0,
        }


def benchmark_agent(agent_class, task_id: str, num_episodes: int = 5):
    """
    Benchmark an agent on a task.
    
    Args:
        agent_class: Agent class to test
        task_id: Task to run on
        num_episodes: Number of episodes to run
    
    Returns:
        Dictionary with episode results
    """
    from src.environment import SREBenchEnvironment
    
    results = {
        "agent": agent_class.__name__,
        "task": task_id,
        "episodes": [],
    }
    
    for ep in range(num_episodes):
        env = SREBenchEnvironment()
        agent = agent_class(env)
        obs = env.reset(task_id)
        
        done = False
        episode_reward = 0.0
        
        while not done and env.step_count < env.max_steps:
            action = agent.act(obs)
            obs, reward, done, info = env.step(action)
            episode_reward += reward.value
        
        results["episodes"].append({
            "episode": ep + 1,
            "steps": env.step_count,
            "reward": episode_reward,
            "resolved": env._check_incident_resolved(),
        })
    
    # Calculate stats
    rewards = [ep["reward"] for ep in results["episodes"]]
    results["avg_reward"] = sum(rewards) / len(rewards)
    results["best_reward"] = max(rewards)
    results["worst_reward"] = min(rewards)
    results["success_rate"] = sum(1 for ep in results["episodes"] if ep["resolved"]) / num_episodes
    
    return results


if __name__ == "__main__":
    from src.environment import SREBenchEnvironment
    
    print("=" * 80)
    print("Benchmarking Baseline Agents")
    print("=" * 80)
    
    # Test on easy scenario
    task = "easy_restart"
    
    for agent_class in [RandomAgent, RuleBasedAgent]:
        print(f"\n\n{agent_class.__name__} on {task}:")
        results = benchmark_agent(agent_class, task, num_episodes=5)
        
        print(f"  Episodes: {results['episodes']}")
        print(f"  Avg Reward: {results['avg_reward']:.3f}")
        print(f"  Best Reward: {results['best_reward']:.3f}")
        print(f"  Success Rate: {results['success_rate']:.1%}")
    
    print("\n✅ Agent benchmarking complete!")
