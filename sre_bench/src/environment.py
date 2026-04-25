"""Compatibility wrapper for `sre-bench/src/environment.py`."""

from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
_source_pkg_root = str(_root / "sre-bench")
if _source_pkg_root not in sys.path:
    sys.path.insert(0, _source_pkg_root)

from src.environment import INCIDENTS, SREBenchEnvironment  # type: ignore  # noqa: E402

__all__ = ["INCIDENTS", "SREBenchEnvironment"]
