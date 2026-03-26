"""
Training examples for SREBench using Stable-Baselines3.
Shows how to train PPO, DQN, A2C agents on incident scenarios.
"""

import numpy as np
from pathlib import Path
import sys

# For local testing
sys.path.insert(0, str(Path(__file__).parent))

try:
    from stable_baselines3 import PPO, A2C, DQN
    from stable_baselines3.common.vec_env import DummyVecEnv
    from stable_baselines3.common.callbacks import BaseCallback
    HAS_SB3 = True
except ImportError:
    HAS_SB3 = False
    print("⚠️  stable-baselines3 not installed. Run: pip install stable-baselines3")

from gymnasium_env import SREBenchGymEnv, SREBenchVectorEnv


class EpisodeLoggerCallback(BaseCallback):
    """Log episode statistics."""
    
    def __init__(self, verbose=0):
        super().__init__(verbose)
        self.episode_rewards = []
        self.episode_lengths = []
    
    def _on_step(self) -> bool:
        if "episode" in self.model.env.get_attr("episode_id"):
            self.episode_rewards.append(self.locals["rewards"])
        return True


def train_ppo(task_id: str = "easy_restart", timesteps: int = 10000, save_path: str = None):
    """
    Train a PPO agent on a task.
    
    Args:
        task_id: Incident scenario
        timesteps: Total training steps
        save_path: Where to save the trained model
    
    Returns:
        Trained agent and episode statistics
    """
    if not HAS_SB3:
        print("stable-baselines3 not installed")
        return None
    
    print(f"\n🚀 Training PPO on {task_id}...")
    
    # Create environment
    env = SREBenchGymEnv(task_id=task_id)
    
    # Create agent
    agent = PPO(
        policy="MlpPolicy",
        env=env,
        learning_rate=1e-3,
        n_steps=2048,
        batch_size=64,
        n_epochs=10,
        verbose=1
    )
    
    # Train
    agent.learn(total_timesteps=timesteps)
    
    # Save
    if save_path:
        agent.save(save_path)
        print(f"✅ Model saved to {save_path}")
    
    return agent


def train_a2c(task_id: str = "easy_restart", timesteps: int = 10000, save_path: str = None):
    """
    Train an A2C agent on a task.
    Faster convergence than PPO for simple tasks.
    """
    if not HAS_SB3:
        print("stable-baselines3 not installed")
        return None
    
    print(f"\n🚀 Training A2C on {task_id}...")
    
    env = SREBenchGymEnv(task_id=task_id)
    
    agent = A2C(
        policy="MlpPolicy",
        env=env,
        learning_rate=1e-3,
        verbose=1
    )
    
    agent.learn(total_timesteps=timesteps)
    
    if save_path:
        agent.save(save_path)
        print(f"✅ Model saved to {save_path}")
    
    return agent


def evaluate_agent(agent, task_id: str = "easy_restart", num_episodes: int = 10):
    """
    Evaluate a trained agent.
    
    Args:
        agent: Trained SB3 agent
        task_id: Task to evaluate on
        num_episodes: Number of evaluation episodes
    
    Returns:
        Dictionary with evaluation metrics
    """
    env = SREBenchGymEnv(task_id=task_id, render_mode="human")
    
    episode_rewards = []
    episode_lengths = []
    successes = 0
    
    for ep in range(num_episodes):
        obs, _ = env.reset()
        episode_reward = 0.0
        length = 0
        
        while True:
            action, _states = agent.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(action)
            
            episode_reward += reward
            length += 1
            
            if terminated or truncated:
                break
        
        episode_rewards.append(episode_reward)
        episode_lengths.append(length)
        
        if info.get("incident_resolved"):
            successes += 1
        
        print(f"  Episode {ep+1}: Reward={episode_reward:.3f}, Steps={length}, Resolved={info.get('incident_resolved')}")
    
    env.close()
    
    results = {
        "task": task_id,
        "episodes": num_episodes,
        "avg_reward": np.mean(episode_rewards),
        "std_reward": np.std(episode_rewards),
        "avg_length": np.mean(episode_lengths),
        "success_rate": successes / num_episodes,
        "rewards": episode_rewards,
        "lengths": episode_lengths,
    }
    
    return results


def curriculum_learning(tasks: list = None, timesteps_per_task: int = 5000):
    """
    Train using curriculum learning: easy → medium → hard.
    
    Args:
        tasks: List of task_ids in order of difficulty
        timesteps_per_task: Training steps per task
    """
    if not HAS_SB3:
        print("stable-baselines3 not installed")
        return None
    
    if tasks is None:
        tasks = ["easy_restart", "medium_cascade", "hard_intermittent"]
    
    print("\n" + "="*80)
    print("CURRICULUM LEARNING: Easy → Medium → Hard")
    print("="*80)
    
    results = {}
    agent = None
    
    for i, task in enumerate(tasks):
        print(f"\n[Task {i+1}/{len(tasks)}] Training on {task}...")
        
        env = SREBenchGymEnv(task_id=task)
        
        if agent is None:
            # First task: create agent
            agent = PPO("MlpPolicy", env, learning_rate=1e-3, verbose=1)
        else:
            # Transfer learning: use existing agent
            agent.env = env
            print(f"  Transferring weights from {tasks[i-1]}")
        
        agent.learn(total_timesteps=timesteps_per_task)
        
        # Evaluate on this task
        eval_results = evaluate_agent(agent, task_id=task, num_episodes=5)
        results[task] = eval_results
        
        print(f"  ✓ Success Rate: {eval_results['success_rate']:.1%}")
    
    return agent, results


def multi_task_learning(tasks: list = None, timesteps: int = 20000):
    """
    Train on multiple tasks simultaneously using vectorized environments.
    """
    if not HAS_SB3:
        print("stable-baselines3 not installed")
        return None
    
    if tasks is None:
        tasks = ["easy_restart", "medium_cascade"]
    
    print("\n" + "="*80)
    print("MULTI-TASK LEARNING")
    print("="*80)
    
    # Create multiple instances
    envs = [SREBenchGymEnv(task_id=task) for task in tasks]
    vec_env = DummyVecEnv([lambda env=e: env for e in envs])
    
    # Train
    agent = PPO("MlpPolicy", vec_env, learning_rate=1e-3, verbose=1)
    agent.learn(total_timesteps=timesteps)
    
    # Evaluate on each task
    print("\nEvaluation:")
    for task in tasks:
        results = evaluate_agent(agent, task_id=task, num_episodes=3)
        print(f"\n  {task}: {results['success_rate']:.1%} success")
    
    return agent


# Example usage
if __name__ == "__main__":
    if not HAS_SB3:
        print("stable-baselines3 required for training. Install with:")
        print("  pip install stable-baselines3")
        print("\nBut the Gymnasium environment is ready to use with any RL framework!")
    else:
        import argparse
        
        parser = argparse.ArgumentParser()
        parser.add_argument("--agent", choices=["ppo", "a2c", "curriculum"], default="ppo")
        parser.add_argument("--task", default="easy_restart")
        parser.add_argument("--timesteps", type=int, default=10000)
        parser.add_argument("--evaluate", action="store_true")
        
        args = parser.parse_args()
        
        if args.agent == "ppo":
            agent = train_ppo(task_id=args.task, timesteps=args.timesteps)
            if args.evaluate:
                evaluate_agent(agent, task_id=args.task)
        
        elif args.agent == "a2c":
            agent = train_a2c(task_id=args.task, timesteps=args.timesteps)
            if args.evaluate:
                evaluate_agent(agent, task_id=args.task)
        
        elif args.agent == "curriculum":
            agent, results = curriculum_learning(timesteps_per_task=args.timesteps//3)
            print("\n" + "="*80)
            print("CURRICULUM LEARNING RESULTS")
            print("="*80)
            for task, res in results.items():
                print(f"\n{task}:")
                print(f"  Avg Reward: {res['avg_reward']:.3f}")
                print(f"  Success Rate: {res['success_rate']:.1%}")
