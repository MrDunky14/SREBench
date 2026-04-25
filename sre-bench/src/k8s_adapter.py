"""Kubernetes command adapter for bridging SREBench actions to real clusters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class KubernetesAdapter:
    """Translate SREBench remediation actions into kubectl commands."""

    namespace: str = "production"
    service_to_deployment: Dict[str, str] = field(default_factory=lambda: {
        "api-gateway": "api-gateway",
        "user-service": "user-service",
        "payment-service": "payment-service",
        "database-primary": "database-primary",
        "database-replica": "database-replica",
        "cache-redis": "cache-redis",
    })

    def _deployment_for(self, service_name: str) -> str:
        """Return mapped deployment name, falling back to the service name."""
        return self.service_to_deployment.get(service_name, service_name)

    def execute(self, action_json: Dict[str, Any]) -> str:
        """Print and return the kubectl command for a remediation action."""
        action_type = action_json.get("action_type", "")
        command = action_json.get("command", "")
        target = action_json.get("target", "")
        params = action_json.get("params", {}) or {}

        if action_type != "remediate":
            msg = f"No-op: action_type '{action_type}' is not a remediation action."
            print(msg)
            return msg

        deployment = self._deployment_for(target)

        if command == "restart":
            kubectl = f"kubectl rollout restart deployment/{deployment} -n {self.namespace}"
        elif command == "scale_up":
            replicas = int(params.get("replicas", 3))
            kubectl = f"kubectl scale deployment/{deployment} --replicas={replicas} -n {self.namespace}"
        elif command == "increase_pool":
            kubectl = (
                f"kubectl set env deployment/{deployment} DB_POOL_MAX="
                f"{int(params.get('new_max', 500))} -n {self.namespace}"
            )
        elif command == "flush_cache":
            kubectl = f"kubectl rollout restart deployment/{deployment} -n {self.namespace}"
        elif command == "rollback":
            kubectl = f"kubectl rollout undo deployment/{deployment} -n {self.namespace}"
        elif command == "failover":
            kubectl = (
                f"kubectl patch deployment/{deployment} -n {self.namespace} "
                "-p '{\"spec\":{\"template\":{\"metadata\":{\"labels\":{\"role\":\"primary\"}}}}}'"
            )
        else:
            kubectl = f"# Unsupported remediation command: {command} (target={target})"

        print(f"[K8S ADAPTER] Running: {kubectl}")
        return kubectl
