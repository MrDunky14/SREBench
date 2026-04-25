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
    "cpu_throttle": [
        "WARN  CPU throttling detected: {throttle_pct}% of cycles throttled",
        "WARN  Request queue depth: {queue_depth} (threshold: 50)",
        "ERROR Request processing exceeded timeout: {timeout}ms",
        "WARN  Thread pool saturated: {active}/{max} active threads",
    ],
    "slow_memory_leak": [
        "DEBUG Heap usage: {heap_mb}MB / {heap_max}MB ({heap_pct}%)",
        "WARN  GC frequency increasing: {gc_count} collections in last minute",
        "DEBUG Object finalizer queue depth: {finalizer_depth}",
        "WARN  Resident memory growing: +{growth_mb}MB in last hour",
    ],
    "disk_pressure": [
        "WARN  Disk usage: {disk_pct}% on /var/lib/postgresql/data",
        "ERROR Write failed: No space left on device (errno=28)",
        "WARN  WAL segment accumulation: {wal_count} segments pending archival",
        "ERROR Checkpoint failed: could not write to file pg_wal",
    ],
    "dns_resolution_failure": [
        "ERROR DNS resolution failed for {hostname}: SERVFAIL",
        "WARN  Upstream connection timeout after DNS lookup delay: {delay}ms",
        "ERROR Failed to resolve service endpoint: {service}.internal.svc",
        "WARN  Falling back to cached DNS entry (TTL expired {ttl_ago}s ago)",
    ],
    "database_deadlock": [
        "ERROR Deadlock detected: transaction {txn_id} waiting on lock held by {blocking_txn}",
        "WARN  Lock wait timeout: {wait_ms}ms on table {table}",
        "ERROR Transaction {txn_id} aborted due to deadlock",
        "WARN  Lock queue depth: {lock_queue} transactions waiting",
    ],
    "tls_cert_expired": [
        "ERROR TLS handshake failed: certificate expired {days_ago} days ago",
        "ERROR SSL_ERROR_EXPIRED_CERT_ALERT from client {client_ip}",
        "WARN  Certificate expiry: CN={cn} expired at {expiry_date}",
        "ERROR Rejecting connection: peer certificate verification failed",
    ],
    "config_drift": [
        "WARN  Config hash mismatch: running={running_hash} expected={expected_hash}",
        "ERROR Feature flag '{flag}' enabled but backend not ready",
        "WARN  Rate limiter threshold changed: {old_rps} -> {new_rps} rps",
        "ERROR Unexpected 503 from upstream after config reload at {reload_time}",
    ],
}


class Infrastructure:
    """Simulates a microservices infrastructure."""
    
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.services: Dict[str, ServiceState] = {}
        self.incident_config = None
        self.affected_services: set = set()
        self._init_services()

    def _jitter(self, value: float, pct: float, floor: float = 0.0, ceiling: float = 10000.0) -> float:
        """Apply bounded gaussian noise so episodes are not strictly identical."""
        sigma = max(0.001, abs(value) * pct)
        return max(floor, min(ceiling, self.rng.gauss(value, sigma)))
    
    def _init_services(self):
        """Initialize all services in healthy state."""
        for name in SERVICES:
            cpu_base = self.rng.uniform(10, 50)
            mem_base = self.rng.uniform(30, 70)
            lat_base = self.rng.uniform(50, 200)
            self.services[name] = ServiceState(
                name=name,
                status="healthy",
                cpu_percent=self._jitter(cpu_base, 0.08, floor=2.0, ceiling=95.0),
                memory_percent=self._jitter(mem_base, 0.08, floor=5.0, ceiling=97.0),
                error_rate_percent=0.0,
                latency_p99_ms=self._jitter(lat_base, 0.10, floor=10.0, ceiling=5000.0),
            )
    
    def inject_incident(self, incident_config: dict):
        """Inject one or more root-cause faults and propagate failures."""
        self.incident_config = incident_config
        configurations = incident_config.get("configurations")
        is_compound = incident_config.get("is_compound", False)

        if configurations or is_compound:
            if not configurations:
                root = incident_config["root_cause_service"]
                fault_type = incident_config["fault_type"]
                configurations = [{"root_cause_service": root, "fault_type": fault_type}]
            self.inject_compound_incident(configurations)
        else:
            root = incident_config["root_cause_service"]
            fault_type = incident_config["fault_type"]
            self._apply_fault(root, fault_type)
            self.affected_services.add(root)
            self._propagate_failures(root)

        # Add a mild decoy signal to one healthy service so agents must correlate evidence.
        self._inject_decoy_anomaly()

    def inject_compound_incident(self, configurations: list):
        """Inject a compound incident across multiple service/fault pairs."""
        for config in configurations:
            root = config["root_cause_service"]
            fault_type = config["fault_type"]
            self._apply_fault(root, fault_type)
            self.affected_services.add(root)

        # Propagate after all root causes are marked, so root services are not overwritten.
        for config in configurations:
            self._propagate_failures(config["root_cause_service"])

    def _inject_decoy_anomaly(self):
        """Apply a subtle non-failing anomaly to a healthy service."""
        candidates = [
            name for name, svc in self.services.items()
            if name not in self.affected_services and svc.status == "healthy"
        ]
        if not candidates:
            return

        decoy = self.rng.choice(candidates)
        svc = self.services[decoy]
        svc.latency_p99_ms = min(900.0, svc.latency_p99_ms + self.rng.uniform(80.0, 180.0))
        svc.error_rate_percent = min(3.5, svc.error_rate_percent + self.rng.uniform(0.2, 1.2))
        svc.log_buffer.append(LogEntry(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            level="WARN",
            message="Transient upstream jitter observed; auto-retry stabilized requests.",
        ))
    
    def _apply_fault(self, service_name: str, fault_type: str):
        """Apply a fault to a service with stochastic metrics."""
        svc = self.services[service_name]
        svc.fault_type = fault_type
        
        if fault_type == "oom_killed":
            svc.status = "down"
            svc.memory_percent = self._jitter(95.0, 0.04, floor=88.0, ceiling=99.5)
            svc.error_rate_percent = self._jitter(95.0, 0.06, floor=80.0, ceiling=100.0)
            svc.cpu_percent = self._jitter(8.0, 0.30, floor=2.0, ceiling=20.0)
            svc.latency_p99_ms = self._jitter(5000.0, 0.15, floor=3000.0, ceiling=8000.0)
            self._gen_logs(service_name, fault_type)
            
        elif fault_type == "connection_pool_exhaustion":
            svc.status = "degraded"
            svc.error_rate_percent = self._jitter(85.0, 0.08, floor=70.0, ceiling=98.0)
            svc.latency_p99_ms = self._jitter(4500.0, 0.12, floor=3000.0, ceiling=7000.0)
            svc.cpu_percent = self._jitter(25.0, 0.15, floor=12.0, ceiling=45.0)
            svc.memory_percent = self._jitter(65.0, 0.10, floor=50.0, ceiling=80.0)
            self._gen_logs(service_name, fault_type)
            
        elif fault_type == "cache_fragmentation":
            # Cache shows as healthy but has subtle issues
            svc.status = "healthy"
            svc.cpu_percent = self._jitter(12.0, 0.20, floor=5.0, ceiling=25.0)
            svc.memory_percent = self._jitter(43.0, 0.12, floor=30.0, ceiling=58.0)
            svc.error_rate_percent = self._jitter(1.5, 0.50, floor=0.0, ceiling=5.0)
            svc.latency_p99_ms = self._jitter(2.0, 0.30, floor=0.5, ceiling=6.0)
            self._update_service_metric(service_name, "cache_hit_ratio", self.rng.randint(62, 78))
            self._gen_logs(service_name, fault_type)
        
        elif fault_type == "network_partition":
            svc.status = "degraded"
            svc.error_rate_percent = self._jitter(65.0, 0.10, floor=45.0, ceiling=85.0)
            svc.latency_p99_ms = self._jitter(3200.0, 0.15, floor=2000.0, ceiling=5500.0)
            svc.cpu_percent = self._jitter(45.0, 0.12, floor=28.0, ceiling=65.0)
            svc.memory_percent = self._jitter(78.0, 0.08, floor=65.0, ceiling=90.0)
            self._update_service_metric(service_name, "replication_lag_ms", self.rng.randint(3000, 8000))
            self._gen_logs(service_name, fault_type)
        
        elif fault_type == "database_replica_sync_failure":
            svc.status = "degraded"
            svc.error_rate_percent = self._jitter(35.0, 0.15, floor=18.0, ceiling=55.0)
            svc.latency_p99_ms = self._jitter(2100.0, 0.12, floor=1200.0, ceiling=3500.0)
            svc.cpu_percent = self._jitter(55.0, 0.10, floor=38.0, ceiling=72.0)
            svc.memory_percent = self._jitter(82.0, 0.06, floor=72.0, ceiling=92.0)
            self._update_service_metric(service_name, "replication_lag_seconds", self.rng.randint(20, 90))
            self._gen_logs(service_name, fault_type)

        elif fault_type == "cpu_throttle":
            svc.status = "degraded"
            svc.cpu_percent = self._jitter(96.0, 0.03, floor=90.0, ceiling=100.0)
            svc.memory_percent = self._jitter(55.0, 0.10, floor=40.0, ceiling=70.0)
            svc.error_rate_percent = self._jitter(40.0, 0.15, floor=20.0, ceiling=60.0)
            svc.latency_p99_ms = self._jitter(3800.0, 0.12, floor=2500.0, ceiling=5500.0)
            self._update_service_metric(service_name, "cpu_throttle_pct", self.rng.randint(60, 90))
            self._gen_logs(service_name, fault_type)

        elif fault_type == "slow_memory_leak":
            # Looks healthy initially but memory is creeping up
            svc.status = "healthy"
            svc.cpu_percent = self._jitter(30.0, 0.15, floor=15.0, ceiling=50.0)
            svc.memory_percent = self._jitter(82.0, 0.06, floor=75.0, ceiling=92.0)
            svc.error_rate_percent = self._jitter(3.0, 0.40, floor=0.5, ceiling=8.0)
            svc.latency_p99_ms = self._jitter(350.0, 0.15, floor=200.0, ceiling=600.0)
            self._update_service_metric(service_name, "heap_growth_mb_per_hour", self.rng.randint(50, 200))
            self._gen_logs(service_name, fault_type)

        elif fault_type == "disk_pressure":
            svc.status = "degraded"
            svc.cpu_percent = self._jitter(60.0, 0.10, floor=40.0, ceiling=80.0)
            svc.memory_percent = self._jitter(70.0, 0.08, floor=55.0, ceiling=85.0)
            svc.error_rate_percent = self._jitter(55.0, 0.12, floor=35.0, ceiling=75.0)
            svc.latency_p99_ms = self._jitter(4200.0, 0.10, floor=3000.0, ceiling=6000.0)
            self._update_service_metric(service_name, "disk_usage_pct", self.rng.randint(92, 99))
            self._gen_logs(service_name, fault_type)

        elif fault_type == "dns_resolution_failure":
            svc.status = "degraded"
            svc.cpu_percent = self._jitter(20.0, 0.20, floor=8.0, ceiling=35.0)
            svc.memory_percent = self._jitter(40.0, 0.10, floor=25.0, ceiling=55.0)
            svc.error_rate_percent = self._jitter(70.0, 0.10, floor=50.0, ceiling=90.0)
            svc.latency_p99_ms = self._jitter(5000.0, 0.08, floor=4000.0, ceiling=8000.0)
            self._gen_logs(service_name, fault_type)

        elif fault_type == "database_deadlock":
            svc.status = "degraded"
            svc.cpu_percent = self._jitter(75.0, 0.10, floor=55.0, ceiling=92.0)
            svc.memory_percent = self._jitter(68.0, 0.08, floor=55.0, ceiling=82.0)
            svc.error_rate_percent = self._jitter(50.0, 0.12, floor=30.0, ceiling=70.0)
            svc.latency_p99_ms = self._jitter(6000.0, 0.10, floor=4000.0, ceiling=9000.0)
            self._update_service_metric(service_name, "deadlock_count", self.rng.randint(5, 25))
            self._gen_logs(service_name, fault_type)

        elif fault_type == "tls_cert_expired":
            svc.status = "degraded"
            svc.cpu_percent = self._jitter(15.0, 0.20, floor=5.0, ceiling=30.0)
            svc.memory_percent = self._jitter(35.0, 0.12, floor=20.0, ceiling=50.0)
            svc.error_rate_percent = self._jitter(90.0, 0.05, floor=80.0, ceiling=100.0)
            svc.latency_p99_ms = self._jitter(100.0, 0.30, floor=20.0, ceiling=300.0)
            self._update_service_metric(service_name, "cert_days_expired", self.rng.randint(1, 30))
            self._gen_logs(service_name, fault_type)

        elif fault_type == "config_drift":
            svc.status = "degraded"
            svc.cpu_percent = self._jitter(45.0, 0.12, floor=30.0, ceiling=65.0)
            svc.memory_percent = self._jitter(60.0, 0.10, floor=45.0, ceiling=75.0)
            svc.error_rate_percent = self._jitter(35.0, 0.18, floor=15.0, ceiling=55.0)
            svc.latency_p99_ms = self._jitter(1800.0, 0.15, floor=1000.0, ceiling=3000.0)
            self._gen_logs(service_name, fault_type)

    def _update_service_metric(self, service_name: str, metric_name: str, metric_value):
        """Merge fault-specific metric into service history without wiping prior signals."""
        svc = self.services[service_name]
        svc.metrics_history[metric_name] = metric_value
    
    def _propagate_failures(self, failed_service: str):
        """Services depending on failed service become degraded with noise."""
        for name, config in SERVICES.items():
            if failed_service in config["depends_on"] and name not in self.affected_services:
                svc = self.services[name]
                svc.status = "degraded"
                svc.error_rate_percent = self._jitter(45.0, 0.15, floor=25.0, ceiling=65.0)
                svc.latency_p99_ms = self._jitter(2800.0, 0.12, floor=1800.0, ceiling=4200.0)
                svc.cpu_percent = self._jitter(65.0, 0.10, floor=48.0, ceiling=82.0)
                svc.memory_percent = self._jitter(72.0, 0.08, floor=58.0, ceiling=85.0)
                self.affected_services.add(name)
                self._propagate_failures(name)
    
    def _gen_logs(self, service_name: str, fault_type: str):
        """Generate realistic logs for a fault."""
        svc = self.services[service_name]
        templates = LOG_TEMPLATES.get(fault_type, [])
        
        for i, template in enumerate(templates[:3]):
            # Prepare all possible format keywords
            format_kwargs = {
                "mem": self.rng.randint(91, 99),
                "gc_ms": self.rng.randint(220, 420),
                "pool_pct": self.rng.randint(95, 100),
                "max_conn": self.rng.choice([180, 200, 220]),
                "timeout": self.rng.choice([3500, 5000, 7000]),
                "n_queued": self.rng.randint(100, 240),
                "hit_ratio": self.rng.randint(62, 78),
                "frag_ratio": round(self.rng.uniform(1.7, 2.6), 2),
                "key": f"user:{self.rng.randint(1000, 99999)}",
                "endpoint": "/api/charge",
                "lag": str(self.rng.randint(3200, 7800)),
                "lag_ms": self.rng.randint(3000, 9000),
                "lag_seconds": self.rng.randint(20, 90),
                "timeout_ms": self.rng.choice([3500, 5000, 7000]),
            }
            
            # Format template with available kwargs (ignore missing ones)
            try:
                msg = template.format(**{k: v for k, v in format_kwargs.items() if "{" + k + "}" in template})
            except (KeyError, ValueError):
                # Fallback if formatting fails
                msg = template
            
            ts = datetime.now().replace(microsecond=0)
            ts = ts.replace(second=max(0, min(59, ts.second - self.rng.randint(0, 20) + i)))
            pid = self.rng.randint(1000, 9999)
            svc.log_buffer.append(LogEntry(
                timestamp=ts.strftime("%Y-%m-%d %H:%M:%S"),
                level=template.split()[0],
                message=f"{msg} [pid={pid}]",
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
            svc.status = "healthy"
            svc.memory_percent = 45.0
            svc.error_rate_percent = 0.0
            svc.cpu_percent = 35.0
            svc.latency_p99_ms = 120.0
            svc.fault_type = None
            self._recover_dependents(target)
            return f"✓ Service {target} restarted successfully. Status: HEALTHY"
        
        elif svc.fault_type == "connection_pool_exhaustion":
            return f"✗ Service {target} restarted but immediately degraded again. Upstream dependency (database-primary) still failing."
        
        elif svc.fault_type == "cache_fragmentation":
            return f"~ Service {target} restarted. Fragmentation persists; consider flush_cache."
        
        elif svc.fault_type == "database_replica_sync_failure":
            svc.status = "healthy"
            svc.memory_percent = 50.0
            svc.error_rate_percent = 0.0
            svc.cpu_percent = 30.0
            svc.latency_p99_ms = 80.0
            svc.fault_type = None
            svc.metrics_history = {}
            self._recover_dependents(target)
            return f"✓ Service {target} restarted. WAL sync restored. Replication recovered."
        
        elif svc.fault_type == "network_partition":
            svc.status = "healthy"
            svc.memory_percent = 55.0
            svc.error_rate_percent = 2.0
            svc.cpu_percent = 35.0
            svc.latency_p99_ms = 150.0
            svc.fault_type = None
            self._recover_dependents(target)
            return f"~ Service {target} restarted. Network connectivity partially restored. Consider failover for full recovery."
        
        elif svc.fault_type == "slow_memory_leak":
            svc.status = "healthy"
            svc.memory_percent = 40.0
            svc.error_rate_percent = 0.0
            svc.cpu_percent = 25.0
            svc.latency_p99_ms = 100.0
            svc.fault_type = None
            svc.metrics_history = {}
            self._recover_dependents(target)
            return f"✓ Service {target} restarted. Memory leak cleared. Heap usage normalized."
        
        elif svc.fault_type == "dns_resolution_failure":
            svc.status = "healthy"
            svc.error_rate_percent = 0.0
            svc.latency_p99_ms = 100.0
            svc.fault_type = None
            self._recover_dependents(target)
            return f"✓ Service {target} restarted. DNS cache flushed. Resolution restored."
        
        elif svc.fault_type == "database_deadlock":
            svc.status = "healthy"
            svc.error_rate_percent = 0.0
            svc.cpu_percent = 30.0
            svc.latency_p99_ms = 80.0
            svc.fault_type = None
            svc.metrics_history = {}
            self._recover_dependents(target)
            return f"✓ Service {target} restarted. Deadlocked transactions killed. Lock queue cleared."
        
        elif svc.fault_type == "cpu_throttle":
            return f"~ Service {target} restarted but CPU throttling persists. Consider scale_up."
        
        elif svc.fault_type == "disk_pressure":
            return f"~ Service {target} restarted but disk pressure persists. Need to clear temp tables."
        
        elif svc.fault_type == "tls_cert_expired":
            return f"~ Service {target} restarted but TLS certificate is still expired. Deploy new certificate."
        
        elif svc.fault_type == "config_drift":
            return f"~ Service {target} restarted with drifted config. Consider rollback to last known good."
        
        else:
            return f"~ Service {target} restarted. No significant state change."
    
    def _recover_dependents(self, service_name: str):
        """Recover services that depend on the given service."""
        for name, config in SERVICES.items():
            if service_name in config["depends_on"] and name in self.affected_services:
                svc = self.services[name]
                svc.status = "healthy"
                svc.error_rate_percent = 0.0
                svc.latency_p99_ms = self.rng.uniform(80, 150)
                svc.cpu_percent = self.rng.uniform(20, 40)
                svc.memory_percent = self.rng.uniform(40, 60)
                self._recover_dependents(name)
    
    def _scale_service(self, target: str, params: dict) -> str:
        """Scale up a service."""
        svc = self.services[target]
        if svc.fault_type == "cpu_throttle":
            svc.status = "healthy"
            svc.cpu_percent = 35.0
            svc.error_rate_percent = 0.0
            svc.latency_p99_ms = 120.0
            svc.fault_type = None
            svc.metrics_history = {}
            self._recover_dependents(target)
            return f"✓ Scaled {target}. CPU throttling resolved. Status: HEALTHY"
        svc.cpu_percent = max(10, svc.cpu_percent - 15)
        svc.memory_percent = max(20, svc.memory_percent - 10)
        return f"✓ Scaled {target}. New CPU: {svc.cpu_percent:.1f}%, Memory: {svc.memory_percent:.1f}%"
    
    def _increase_pool(self, target: str, params: dict) -> str:
        """Increase connection pool size."""
        svc = self.services[target]
        
        if svc.fault_type == "connection_pool_exhaustion":
            svc.fault_type = None
            svc.status = "healthy"
            svc.error_rate_percent = 0.0
            svc.latency_p99_ms = 45.0
            svc.cpu_percent = 35.0
            svc.memory_percent = 55.0
            self._recover_dependents(target)
            return f"✓ Increased connection pool on {target} to {params.get('new_max', 500)}. Status: HEALTHY. Cascading failures resolve."
        
        if svc.fault_type == "disk_pressure":
            svc.fault_type = None
            svc.status = "healthy"
            svc.error_rate_percent = 0.0
            svc.latency_p99_ms = 60.0
            svc.cpu_percent = 30.0
            svc.memory_percent = 50.0
            svc.metrics_history = {}
            self._recover_dependents(target)
            return f"✓ Cleared temp tables and WAL segments on {target}. Disk pressure resolved. Status: HEALTHY"
        
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
                        s.latency_p99_ms = self.rng.uniform(100, 200)
                        # Recover services that depend on this one
                        self._recover_dependents(name)
            return f"✓ Flushed cache on {target}. Fragmentation resolved. Cache hit ratio recovered to 97%."
        
        return f"~ Flushed cache on {target}. No fragmentation detected."
    
    def _rollback(self, target: str) -> str:
        """Rollback a service — partial recovery only, not a universal fix."""
        svc = self.services[target]
        if svc.fault_type is None and svc.status == "healthy":
            return f"~ Nothing to rollback on {target}. Service is already healthy."
        
        # Config drift and TLS cert are fixed by rollback
        if svc.fault_type == "config_drift":
            svc.status = "healthy"
            svc.error_rate_percent = 0.0
            svc.latency_p99_ms = 100.0
            svc.cpu_percent = 25.0
            svc.fault_type = None
            self._recover_dependents(target)
            return f"✓ Rolled back {target} to last known good config. Status: HEALTHY"
        
        if svc.fault_type == "tls_cert_expired":
            svc.status = "healthy"
            svc.error_rate_percent = 0.0
            svc.latency_p99_ms = 80.0
            svc.fault_type = None
            self._recover_dependents(target)
            return f"✓ Rolled back {target} with valid TLS certificate. Status: HEALTHY"
        
        # Generic rollback — partial relief only
        svc.error_rate_percent = max(0, svc.error_rate_percent * 0.6)
        svc.latency_p99_ms = max(50, svc.latency_p99_ms * 0.7)
        if svc.error_rate_percent < 5.0:
            svc.status = "healthy"
            svc.fault_type = None
        else:
            svc.status = "degraded"
        return f"~ Rolled back {target}. Partial recovery — error rate now {svc.error_rate_percent:.1f}%. Root cause may persist."
    
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
