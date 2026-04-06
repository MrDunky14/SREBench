"""ASGI app entrypoint expected by OpenEnv validators."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRE_BENCH_DIR = REPO_ROOT / "sre-bench"
if str(SRE_BENCH_DIR) not in sys.path:
    sys.path.insert(0, str(SRE_BENCH_DIR))

from src.server import app  # noqa: E402

__all__ = ["app"]


def main():
    """Entrypoint required by OpenEnv validation checks."""
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server.app:app", host="0.0.0.0", port=7860)
