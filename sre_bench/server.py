"""Compatibility server module for `python -m sre_bench.server`."""

from __future__ import annotations

import sys
from pathlib import Path

import uvicorn


def main() -> None:
    """Run SREBench FastAPI server with default local settings."""
    source_root = str(Path(__file__).resolve().parents[1] / "sre-bench")
    if source_root not in sys.path:
        sys.path.insert(0, source_root)
    uvicorn.run("src.server:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
