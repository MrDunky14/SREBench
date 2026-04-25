"""Compatibility wrapper for `sre-bench/src/k8s_adapter.py`."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_impl_module():
    root = Path(__file__).resolve().parents[2]
    impl_path = root / "sre-bench" / "src" / "k8s_adapter.py"
    spec = importlib.util.spec_from_file_location("srebench_k8s_impl", impl_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module at {impl_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_impl = _load_impl_module()
KubernetesAdapter = _impl.KubernetesAdapter

__all__ = ["KubernetesAdapter"]
