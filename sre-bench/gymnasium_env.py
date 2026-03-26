"""
Gymnasium wrapper for SREBench environment.
Converts the OpenEnv environment to standard gym.Env interface.
"""

import gymnasium as gym
from gymnasium import spaces
import numpy as np
from typing import Any, Dict, Tuple
import sys
from pathlib import Path

# Add parent path for imports
sys.path.insert(0, str(Path(__file__).parent / 'sre-bench'))

from sre_bench.src.environment import SREBenchEnvironment, INCIDENTS
from sre_bench.src.models import IncidentAction


class SREBenchGymEnv(gym.Env):
    """
    Gymnasium wrapper for SREBench environment.
    
    Observations: Flattened vector of service metrics
    Actions: Discrete action space (action_type, command, target combinations)
    Rewards: Dense multi-component rewards
    """
    
    metadata = {"render_modes": ["human"], "render_fps": 1}
    
    def __init__(self, task_id: str = "easy_restart", render_mode: str = None):
        """
        Initialize the environment.
        
        Args:
            task_id: Incident scenario to load
            render_mode: "human" for printing episode details
        """
        self.task_id = task_id
        self.render_mode = render_mode
        self.env = SREBenchEnvironment()
        
        # Define action space
        # Actions: 4 action_types × 8 commands × 6 services = 192 discrete actions
        self.action_types = ["investigate", "diagnose", "remediate", "give_up"]
        self.commands = [
            "check_logs", "check_metrics", "check_connections",
            "restart", "scale_up", "increase_pool", "flush_cache", "failover"
        ]
        self.targets = [
            "api-gateway", "user-service", "payment-service",
            "database-primary", "database-replica", "cache-redis"
        ]
        
        self.action_space = spaces.Discrete(len(self.action_types) * len(self.commands) * len(self.targets))
        
        # Define observation space
        # 6 services × 5 metrics (status, cpu%, mem%, error%, p99ms) = 30 values
        # + 1 for steps_taken, 1 for sla_remaining = 32 total
        self.observation_space = spaces.Box(
            low=0.0, high=100.0, shape=(32,), dtype=np.float32
        )
        
        self.current_obs = None
        self.episode_id = None
    
    def _action_to_incident_action(self, action: int) -> IncidentAction:
        """Convert discrete action to IncidentAction."""
        # Decode action
        action_type_idx = action // (len(self.commands) * len(self.targets))
        command_idx = (action % (len(self.commands) * len(self.targets))) // len(self.targets)
        target_idx = action % len(self.targets)
        
        return IncidentAction(
            action_type=self.action_types[action_type_idx],
            command=self.commands[command_idx],
            target=self.targets[target_idx],
            params={}
        )
    
    def _obs_to_vector(self, obs) -> np.ndarray:
        """Convert observation to flattened vector."""
        vector = []
        
        # Service metrics (6 services × 5 metrics)
        for svc in obs.system_dashboard:
            status_val = {"healthy": 0.0, "degraded": 50.0, "down": 100.0}.get(svc.status, 50.0)
            vector.extend([
                status_val,
                svc.cpu_percent,
                svc.memory_percent,
                svc.error_rate_percent,
                svc.latency_p99_ms / 50.0  # normalize to ~0-100
            ])
        
        # Episode state
        vector.append(float(obs.steps_taken))
        vector.append(obs.sla_remaining_minutes)
        
        return np.array(vector, dtype=np.float32)
    
    def reset(self, seed: int = None, options: Dict[str, Any] = None) -> Tuple[np.ndarray, Dict]:
        """Reset environment to initial state."""
        super().reset(seed=seed)
        
        obs = self.env.reset(self.task_id)
        self.current_obs = obs
        self.episode_id = self.env.episode_id
        
        return self._obs_to_vector(obs), {"episode_id": self.episode_id}
    
    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        """
        Execute one step in the environment.
        
        Returns:
            observation: Flattened vector of service metrics
            reward: Sum of reward components
            terminated: If episode ended (success or failure)
            truncated: If max steps reached
            info: Additional info (episode_id, breakdown, etc.)
        """
        incident_action = self._action_to_incident_action(action)
        
        obs, reward, done, info = self.env.step(incident_action)
        self.current_obs = obs
        
        # Determine termination
        terminated = done and self.env._check_incident_resolved()
        truncated = done and not terminated
        
        info.update({
            "episode_id": self.episode_id,
            "reward_breakdown": reward.breakdown,
            "incident_resolved": self.env._check_incident_resolved(),
            "steps": self.env.step_count,
        })
        
        return self._obs_to_vector(obs), float(reward.value), terminated, truncated, info
    
    def render(self) -> None:
        """Render the current state."""
        if self.render_mode == "human":
            print(f"\n[Episode {self.episode_id}] Step {self.env.step_count}/{self.env.max_steps}")
            print(f"Alert: {self.current_obs.alert_message.split(chr(10))[0]}")
            print(f"Services:")
            for svc in self.current_obs.system_dashboard:
                print(f"  {svc.name}: {svc.status} | CPU: {svc.cpu_percent:.1f}% | Errors: {svc.error_rate_percent:.1f}%")
    
    def close(self) -> None:
        """Close environment."""
        pass


class SREBenchVectorEnv(gym.Env):
    """
    Vectorized environment for parallel training.
    Runs multiple instances of SREBenchGymEnv in parallel.
    """
    
    def __init__(self, num_envs: int = 4, task_id: str = "easy_restart"):
        """Initialize vectorized environment."""
        self.num_envs = num_envs
        self.envs = [SREBenchGymEnv(task_id=task_id) for _ in range(num_envs)]
        
        # Copy spaces from first env
        self.action_space = self.envs[0].action_space
        self.observation_space = spaces.Box(
            low=0.0, high=100.0, shape=(num_envs, 32), dtype=np.float32
        )
    
    def reset(self, seed: int = None) -> Tuple[np.ndarray, Dict]:
        """Reset all environments."""
        observations = []
        infos = {}
        
        for i, env in enumerate(self.envs):
            obs, info = env.reset(seed=seed)
            observations.append(obs)
            infos[i] = info
        
        return np.stack(observations), infos
    
    def step(self, actions: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, Dict]:
        """Step all environments."""
        observations = []
        rewards = []
        terminateds = []
        truncateds = []
        infos = {}
        
        for i, (env, action) in enumerate(zip(self.envs, actions)):
            obs, reward, terminated, truncated, info = env.step(int(action))
            observations.append(obs)
            rewards.append(reward)
            terminateds.append(terminated)
            truncateds.append(truncated)
            infos[i] = info
        
        return (
            np.stack(observations),
            np.array(rewards, dtype=np.float32),
            np.array(terminateds, dtype=bool),
            np.array(truncateds, dtype=bool),
            infos
        )
    
    def close(self) -> None:
        """Close all environments."""
        for env in self.envs:
            env.close()


if __name__ == "__main__":
    # Test the environment
    print("Testing SREBenchGymEnv...")
    env = SREBenchGymEnv(task_id="easy_restart", render_mode="human")
    
    obs, info = env.reset()
    print(f"Observation shape: {obs.shape}")
    print(f"Action space: {env.action_space}")
    
    for step in range(5):
        action = env.action_space.sample()
        obs, reward, terminated, truncated, info = env.step(action)
        env.render()
        print(f"  Reward: {reward:.3f}")
        
        if terminated or truncated:
            break
    
    env.close()
    print("\n✅ Gymnasium environment working!")
