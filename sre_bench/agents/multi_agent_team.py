"""CLI wrapper for the implementation in `sre-bench/agents/multi_agent_team.py`."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_impl_module():
    root = Path(__file__).resolve().parents[2]
    impl_path = root / "sre-bench" / "agents" / "multi_agent_team.py"
    spec = importlib.util.spec_from_file_location("srebench_multi_agent_impl", impl_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module at {impl_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_impl = _load_impl_module()

LLMAdapter = _impl.LLMAdapter
build_workflow = _impl.build_workflow
run_episode = _impl.run_episode
main = _impl.main


if __name__ == "__main__":
    main()
