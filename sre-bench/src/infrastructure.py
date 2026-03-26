"""Infrastructure simulator for SREBench environment."""
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime


@dataclass
class LogEntry:
    """A single log entry."""
    timestamp: str
    level: str  # INFO, WARN, ERROR
    message: str


@dataclass
class ServiceState:
    """Internal state of a service."""
    name: str
    status: str  # healthy, degraded, down
    cpu_percent: float
    memory_percent: float
    error_rate_percent: float
    latency_p99_ms: float
    fault_type: Optional[str] = None
    log_buffer: List[LogEntry] = field(default_factory=list)
    metrics_history: Dict = field(default_factory=dict)
    
    def to_dict(self):
        return {
            "name": self.name,
            "status": self.status,
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "error_rate_percent": self.error_rate_percent,
            "latency_p99_ms": self.latency_p99_ms,
        }


SERVICES = {
    "api-gateway": {"depends_on": ["user-service", "payment-service"]},
    "user-service": {"depends_on": ["database-primary", "cache-redis"]},
    "payment-service": {"depends_on": ["database-primary", "cache-redis"]},
    "database-primary": {"depends_on": []},
    "database-replica": {"depends_on": ["database-primary"]},
    "cache-redis": {"depends_on": []},
}

LOG_TEMPLATES = {
    "oom_killed": [
        "WARN  Memory usage at {mem}% - approaching limit",
        "WARN  GC pause: {gc_ms}ms (threshold: 200ms)",
        "ERROR Java heap space: OutOfMemoryError",
        "ERROR Service crashed - exit code 137 (OOMKilled)",
    ],
    "connection_pool_exhaustion": [
        "WARN  Connection pool utilization at {pool_pct}%",
        "ERROR Cannot acquire connection: pool exhausted (max={max_conn})",
        "ERROR Request failed: ConnectionTimeoutException after {timeout}ms",
        "WARN  {n_queued} requests queued waiting for database connection",
    ],
    "cache_fragmentation": [
        "DEBUG Cache hit ratio: {hit_ratio}% (normal: >95%)",
        "WARN  Memory fragmentation ratio: {frag_ratio} (threshold: 1.5)",
        "DEBUG Evicting key {key} due to memory pressure",
        "INFO  Fallback to database for cache miss on {endpoint}",
    ],
    "network_partition": [
        "ERROR Cannot reach database-primary: timeout after {timeout}ms",
        "WARN  Replication lag detected: {lag}ms (normal: <10ms)",
        "ERROR Failed to receive ACK from replica-primary link",
        "WARN  Read inconsistency: stale data from replica detected",
    ],
    "database_replica_sync_failure": [
        "ERROR Replication failed: WAL sync failed",
        "WARN  Replica sync lag: {lag_seconds}s (threshold: 1s)",
        "ERROR Replication error: master down, replica cannot connect",
        "ERROR Write failed: cannot ensure replica durability",
    ],
}


class Infrastructure:
    """Simulates a microservices infrastructure."""
    
    def __init__(self, seed: int = 42):
        random.seed(seed)
        self.services: Dict[str, ServiceState] = {}
        self.incident_config = None
        self.affected_services: set = set()
        self._init_services()
    
    def _init_services(self):
        """Initialize all services in healthy state."""
        for name in SERVICES:
            self.services[name] = ServiceState(
                name=name,
                status="healthy",
                cpu_percent=random.uniform(10, 50),
                memory_percent=random.uniform(30, 70),
                error_rate_percent=0.0,
                latency_p99_ms=random.uniform(50, 200),
            )
    
    def inject_incident(self, incident_config: dict):
        """Inject root cause and propagate failures."""
        self.incident_config = incident_config
        root = incident_config["root_cause_service"]
        fault_type = incident_config["fault_type"]
        
        # Apply fault to root cause service
        self._apply_fault(root, fault_type)
        self.affected_services.add(root)
        
        # Propagate through dependencies
        self._propagate_failures(root)
    
    def _apply_fault(self, service_name: str, fault_type: str):
        """Apply a fault to a service."""
        svc = self.services[service_name]
        svc.fault_type = fault_type
        
        if fault_type == "oom_killed":
            svc.status = "down"
            svc.memory_percent = 98.0
            svc.error_rate_percent = 100.0
            svc.cpu_percent = 5.0
            svc.latency_p99_ms = 5000.0
            self._gen_logs(service_name, fault_type)
            
        elif fault_type == "connection_pool_exhaustion":
            svc.status = "degraded"
            svc.error_rate_percent = 85.0
            svc.latency_p99_ms = 4500.0
            svc.cpu_percent = 25.0
            svc.memory_percent = 65.0
            self._gen_logs(service_name, fault_type)
            
        elif fault_type == "cache_fragmentation":
            # Cache shows as healthy but has subtle issues
            svc.status = "healthy"
            svc.cpu_percent = 12.0
            svc.memory_percent = 43.0
            svc.error_rate_percent = 0.0
            svc.latency_p99_ms = 2.0
            svc.metrics_history = {"cache_hit_ratio": 72}  # degraded from normal 98%
            self._gen_logs(service_name, fault_type)
        
        elif fault_type == "network_partition":
            # Network partition between primary and replica
            svc.status = "degraded"
            svc.error_rate_percent = 65.0
            svc.latency_p99_ms = 3200.0
            svc.cpu_percent = 45.0
            svc.memory_percent = 78.0
            svc.metrics_history = {"replication_lag_ms": 5000}  # High lag
            self._gen_logs(service_name, fault_type)
        
        elif fault_type == "database_replica_sync_failure":
            # Database replica cannot sync
            svc.status = "degraded"
            svc.error_rate_percent = 35.0
            svc.latency_p99_ms = 2100.0
            svc.cpu_percent = 55.0
            svc.memory_percent = 82.0
            svc.metrics_history = {"replication_lag_seconds": 45}  # Severe lag
            self._gen_logs(service_name, fault_type)
    
    def _propagate_failures(self, failed_service: str):
        """Services depending on failed service become degraded."""
        for name, config in SERVICES.items():
            if failed_service in config["depends_on"] and name not in self.affected_services:
                svc = self.services[name]
                svc.status = "degraded"
                svc.error_rate_percent = 45.0
                svc.latency_p99_ms = 2800.0
                svc.cpu_percent = 65.0
                svc.memory_percent = 72.0
                self.affected_services.add(name)
                self._propagate_failures(name)
    
    def _gen_logs(self, service_name: str, fault_type: str):
        """Generate realistic logs for a fault."""
        svc = self.services[service_name]
        templates = LOG_TEMPLATES.get(fault_type, [])
        
        for i, template in enumerate(templates[:3]):
            # Prepare all possible format keywords
            format_kwargs = {
                "mem": 95,
                "gc_ms": 250,
                "pool_pct": 100,
                "max_conn": 200,
                "timeout": 5000,
                "n_queued": 150,
                "hit_ratio": 72,
                "frag_ratio": 2.1,
                "key": "user:12345",
                "endpoint": "/api/charge",
                "lag": "5000ms",
                "lag_ms": 5000,
                "lag_seconds": 45,
                "timeout_ms": 5000,
            }
            
            # Format template with available kwargs (ignore missing ones)
            try:
                msg = template.format(**{k: v for k, v in format_kwargs.items() if "{" + k + "}" in template})
            except (KeyError, ValueError):
                # Fallback if formatting fails
                msg = template
            
            svc.log_buffer.append(LogEntry(
                timestamp=f"2024-01-15 03:42:{10+i:02d}",
                level=template.split()[0],
                message=msg,
            ))
    
    def execute_action(self, action) -> str:
        """Execute an agent action."""
        cmd = action.command
        target = action.target
        
        if target not in self.services:
            return f"Service '{target}' not found."
        
        if cmd == "check_logs":
            return self._check_logs(target, action.params)
        elif cmd == "check_metrics":
            return self._check_metrics(target, action.params)
        elif cmd == "check_connections":
            return self._check_connections(target)
        elif cmd == "restart":
            return self._restart_service(target)
        elif cmd == "scale_up":
            return self._scale_service(target, action.params)
        elif cmd == "increase_pool":
            return self._increase_pool(target, action.params)
        elif cmd == "flush_cache":
            return self._flush_cache(target)
        elif cmd == "rollback":
            return self._rollback(target)
        elif cmd == "failover":
            return self._failover(target)
        else:
            return f"Unknown command: {cmd}"
    
    def _check_logs(self, target: str, params: dict) -> str:
        """Return logs for a service."""
        svc = self.services[target]
        severity = params.get("severity", "ALL")
        last_n = params.get("last_n", 10)
        
        logs = svc.log_buffer
        if severity != "ALL":
            logs = [l for l in logs if l.level == severity]
        
        if not logs:
            return f"[No logs found for {target}]"
        
        return "\n".join(f"{l.timestamp} {l.level}  {l.message}" for l in logs[-last_n:])
    
    def _check_metrics(self, target: str, params: dict) -> str:
        """Return metrics for a service."""
        svc = self.services[target]
        metric = params.get("metric", "all")
        
        if metric == "all":
            return f"{target} metrics:\n  CPU: {svc.cpu_percent:.1f}%\n  Memory: {svc.memory_percent:.1f}%\n  Error Rate: {svc.error_rate_percent:.1f}%\n  Latency P99: {svc.latency_p99_ms:.0f}ms"
        elif metric == "cache_hit_ratio":
            hit_ratio = svc.metrics_history.get("cache_hit_ratio", 98)
            return f"{target} cache hit ratio: {hit_ratio}% (normal: >95%)"
        elif metric == "connections":
            return f"{target} active connections: {int(svc.memory_percent * 2)} (pool max: 200)"
        else:
            return f"{target} {metric}: {getattr(svc, metric + '_percent', 'N/A')}"
    
    def _check_connections(self, target: str) -> str:
        """Check connections for a service."""
        svc = self.services[target]
        return f"{target} active connections: {int(svc.memory_percent * 2)}/200 (pool utilization: {min(int(svc.memory_percent * 2 / 200 * 100), 100)}%)"
    
    def _restart_service(self, target: str) -> str:
        """Restart a service."""
        svc = self.services[target]
        
        if svc.fault_type == "oom_killed":
            # Restart fixes OOM
            svc.status = "healthy"
            svc.memory_percent = 45.0
            svc.error_rate_percent = 0.0
            svc.cpu_percent = 35.0
            svc.latency_p99_ms = 120.0
            svc.fault_type = None
            # Also recover dependents
            self._recover_dependents(target)
            return f"✓ Service {target} restarted successfully. Status: HEALTHY"
        
        elif svc.fault_type == "connection_pool_exhaustion":
            # Restarting doesn't fix pool exhaustion; returns to degraded immediately
            return f"✗ Service {target} restarted but immediately degraded again. Upstream dependency (database-primary) still failing."
        
        elif svc.fault_type == "cache_fragmentation":
            # Restarting cache without handling fragmentation doesn't help much
            return f"~ Service {target} restarted. Fragmentation persists; consider flush_cache."
        
        else:
            return f"~ Service {target} restarted. No significant state change."
    
    def _recover_dependents(self, service_name: str):
        """Recover services that depend on the given service."""
        for name, config in SERVICES.items():
            if service_name in config["depends_on"] and name in self.affected_services:
                svc = self.services[name]
                svc.status = "healthy"
                svc.error_rate_percent = 0.0
                svc.latency_p99_ms = random.uniform(80, 150)
                svc.cpu_percent = random.uniform(20, 40)
                svc.memory_percent = random.uniform(40, 60)
                self._recover_dependents(name)
    
    def _scale_service(self, target: str, params: dict) -> str:
        """Scale up a service."""
        svc = self.services[target]
        svc.cpu_percent = max(10, svc.cpu_percent - 15)
        svc.memory_percent = max(20, svc.memory_percent - 10)
        return f"✓ Scaled {target}. New CPU: {svc.cpu_percent:.1f}%, Memory: {svc.memory_percent:.1f}%"
    
    def _increase_pool(self, target: str, params: dict) -> str:
        """Increase connection pool size."""
        svc = self.services[target]
        
        if svc.fault_type == "connection_pool_exhaustion":
            # Fixing pool exhaustion should recover the service
            svc.fault_type = None
            svc.status = "healthy"
            svc.error_rate_percent = 0.0
            svc.latency_p99_ms = 45.0
            svc.cpu_percent = 35.0
            svc.memory_percent = 55.0
            # Also recover dependents
            self._recover_dependents(target)
            return f"✓ Increased connection pool on {target} to {params.get('new_max', 500)}. Status: HEALTHY. Cascading failures resolve."
        
        return f"~ Increased pool on {target}, but no connection exhaustion detected."
    
    def _flush_cache(self, target: str) -> str:
        """Flush cache and clear fragmentation."""
        svc = self.services[target]
        
        if svc.fault_type == "cache_fragmentation":
            # Flushing resolves fragmentation
            svc.fault_type = None
            svc.metrics_history["cache_hit_ratio"] = 97  # Recovery
            svc.status = "healthy"
            # Reset affected downstream services
            for name in ["payment-service", "user-service"]:
                if name in self.services:
                    s = self.services[name]
                    if s.status == "degraded":
                        s.status = "healthy"
                        s.error_rate_percent = 0.0
                        s.latency_p99_ms = random.uniform(100, 200)
                        # Recover services that depend on this one
                        self._recover_dependents(name)
            return f"✓ Flushed cache on {target}. Fragmentation resolved. Cache hit ratio recovered to 97%."
        
        return f"~ Flushed cache on {target}. No fragmentation detected."
    
    def _rollback(self, target: str) -> str:
        """Rollback a service."""
        svc = self.services[target]
        svc.status = "healthy"
        svc.error_rate_percent = 0.0
        svc.fault_type = None
        return f"✓ Rolled back {target}. Status: HEALTHY"
    
    def _failover(self, target: str) -> str:
        """Failover to replica (database only)."""
        if target == "database-primary":
            # Simulate failover to replica
            replica = self.services["database-replica"]
            replica.status = "healthy"
            replica.error_rate_percent = 0.0
            return f"✓ Failed over from {target} to database-replica. Primary replica is now serving traffic."
        return f"~ Failover not applicable for {target}."
    
    def get_all_services(self) -> List[Dict]:
        """Get status of all services."""
        return [svc.to_dict() for svc in self.services.values()]
