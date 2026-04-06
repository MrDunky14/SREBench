"""
Expert Task Diagnosis Module for SREBench

This module provides specialized strategies for the two expert-level tasks:
1. expert_network_partition: Database primary-replica network isolation
2. expert_database_replica_sync: Replica synchronization with primary WAL
"""

from typing import Dict, Any, List


class ExpertTaskDiagnoser:
    """Specialized diagnosis strategies for expert-level SRE tasks."""
    
    # Expert Network Partition patterns
    NETWORK_PARTITION_SIGNS = {
        "replication_disconnected": [
            "connection refused",
            "connection timeout",
            "connection reset",
            "network unreachable",
            "replica.*disconnected",
            "primary.*disconnected",
        ],
        "replication_lag_high": [
            "replication_lag",
            "lag_ms.*[1-9][0-9]{3,}",  # lag > 1000ms
            "lag_seconds.*[3-9][0-9]",  # lag > 30s
        ],
        "replica_status_bad": [
            "replica_status.*fail",
            "replica_status.*error",
            "replication_active.*false",
            "connected.*false",
        ]
    }
    
    # Database Replica Sync patterns
    REPLICA_SYNC_SIGNS = {
        "wal_mismatch": [
            "wal.*mismatch",
            "wal.*position",
            "write.ahead.log",
            "primary_lsn.*replica_lsn",
            "xlog.*position",
        ],
        "replication_slot_broken": [
            "replication_slot.*broken",
            "slot_type.*fail",
            "slot_restart_lsn",
        ],
        "sync_lag": [
            "sync_lag_ms.*[1-9][0-9]{2,}",  # > 100ms
            "apply_lag.*[0-9]+",
            "sync_timeout",
        ]
    }
    
    @staticmethod
    def diagnose_network_partition(obs: Dict[str, Any], step_no: int) -> Dict[str, str]:
        """
        Diagnose network partition between primary and replica.
        
        Returns: (target_service, root_cause)
        """
        # Strategy phases based on step
        if step_no <= 2:
            return {
                "action": "investigate_logs",
                "target": "database-primary",
                "params": {"log_type": "connection", "severity": "ERROR"}
            }
        
        if step_no <= 4:
            return {
                "action": "check_metrics",
                "target": "database-replica",
                "params": {"metrics": ["replication_lag_seconds", "connected"]}
            }
        
        if step_no <= 6:
            return {
                "action": "check_metrics",
                "target": "database-primary",
                "params": {"metrics": ["replica_count", "connected_replicas"]}
            }
        
        # Commit to diagnosis by step 7
        return {
            "action": "submit_diagnosis",
            "target": "database-primary",
            "root_cause": "network_partition"
        }
    
    @staticmethod
    def diagnose_replica_sync(obs: Dict[str, Any], step_no: int) -> Dict[str, str]:
        """
        Diagnose replica synchronization failure with primary.
        
        Returns: (target_service, root_cause)
        """
        if step_no <= 2:
            return {
                "action": "investigate_logs",
                "target": "database-replica",
                "params": {"log_type": "replication", "severity": "ERROR"}
            }
        
        if step_no <= 4:
            return {
                "action": "check_metrics",
                "target": "database-replica",
                "params": {"metrics": ["wal_position", "sync_lag_ms"]}
            }
        
        if step_no <= 6:
            return {
                "action": "check_metrics",
                "target": "database-primary",
                "params": {"metrics": ["primary_xlog_pos", "write_lag"]}
            }
        
        if step_no <= 8:
            # Check for WAL-specific issues
            return {
                "action": "investigate_logs",
                "target": "database-replica",
                "params": {"log_type": "wal", "severity": "WARN"}
            }
        
        # Commit diagnosis by step 9
        return {
            "action": "submit_diagnosis",
            "target": "database-replica",
            "root_cause": "replication_lag"
        }
    
    @staticmethod
    def extract_relevant_metrics(obs: Dict[str, Any], task_id: str) -> Dict[str, Any]:
        """Extract metrics most relevant to the task."""
        metrics = obs.get("metrics", {})
        relevant_keys = []
        
        if "network_partition" in task_id:
            relevant_keys = [
                k for k in metrics.keys() 
                if any(x in k.lower() for x in 
                       ["replication", "lag", "connection", "network"])
            ]
        
        elif "replica_sync" in task_id:
            relevant_keys = [
                k for k in metrics.keys()
                if any(x in k.lower() for x in
                       ["wal", "sync", "lag", "position", "replica"])
            ]
        
        return {k: metrics[k] for k in relevant_keys if k in metrics}
    
    @staticmethod
    def detect_expert_signals(obs: Dict[str, Any], task_id: str) -> List[str]:
        """Detect diagnostic signals in logs/metrics."""
        signals = []
        last_result = str(obs.get("last_action_result", "")).lower()
        
        # Check against known patterns
        if "network_partition" in task_id:
            patterns = ExpertTaskDiagnoser.NETWORK_PARTITION_SIGNS
        else:
            patterns = ExpertTaskDiagnoser.REPLICA_SYNC_SIGNS
        
        for category, keywords in patterns.items():
            for keyword in keywords:
                if keyword in last_result:
                    signals.append(category)
                    break
        
        return signals


# Expert task prompt templates
EXPERT_NETWORK_PARTITION_HINT = (
    "This task involves a network partition between the primary database and its replica. "
    "The replica cannot communicate with the primary due to network failure. "
    "Look for: connection timeouts, replica disconnected messages, replication lag > 30 seconds, "
    "network unreachable errors. Diagnose as 'network_partition'."
)

EXPERT_REPLICA_SYNC_HINT = (
    "This task involves a replica that has fallen out of sync with the primary database. "
    "The replica's WAL (Write-Ahead Log) position lags behind the primary. "
    "Look for: WAL position mismatches, replication slot errors, sync lag > 100ms, "
    "slot restart LSN changes. Diagnose as 'replication_lag'."
)


# Integration example for inference.py
def enhanced_fallback_for_expert_tasks(
    obs: Dict[str, Any], 
    step_no: int, 
    task_id: str
) -> Dict[str, Any]:
    """
    Enhanced fallback specifically tuned for expert tasks.
    
    Usage in inference.py:
        if "expert" in task_id:
            return enhanced_fallback_for_expert_tasks(obs, step_no, task_id)
    """
    diagnoser = ExpertTaskDiagnoser()
    
    if "network_partition" in task_id:
        diagnosis = diagnoser.diagnose_network_partition(obs, step_no)
    elif "replica_sync" in task_id:
        diagnosis = diagnoser.diagnose_replica_sync(obs, step_no)
    else:
        # Generic expert fallback
        return {
            "action_type": "investigate",
            "command": "check_logs",
            "target": "database-primary",
            "params": {"severity": "ERROR", "last_n": 20},
        }
    
    # Convert internal format to OpenEnv format
    if diagnosis.get("action") == "investigate_logs":
        return {
            "action_type": "investigate",
            "command": "check_logs",
            "target": diagnosis["target"],
            "params": diagnosis.get("params", {}),
        }
    
    elif diagnosis.get("action") == "check_metrics":
        return {
            "action_type": "investigate",
            "command": "check_metrics",
            "target": diagnosis["target"],
            "params": diagnosis.get("params", {}),
        }
    
    elif diagnosis.get("action") == "submit_diagnosis":
        return {
            "action_type": "diagnose",
            "command": "submit_diagnosis",
            "target": diagnosis["target"],
            "params": {"root_cause": diagnosis["root_cause"]},
        }
    
    # Fallback to generic investigate
    return {
        "action_type": "investigate",
        "command": "check_logs",
        "target": "database-primary",
        "params": {"severity": "ERROR", "last_n": 15},
    }
