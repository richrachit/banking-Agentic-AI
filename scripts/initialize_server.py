"""Prepare persistent demo data and local development model artifacts once."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(__import__("os").environ.get("BANKING_DATA_DIR", ROOT / "data"))
MARKER = DATA_DIR / ".server-initialized.json"


def run(*arguments: str) -> None:
    subprocess.run([sys.executable, *arguments], cwd=ROOT, check=True)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if MARKER.exists():
        print(f"Server data already initialized: {MARKER}")
        return

    run("-m", "banking_agents", "seed-demo")
    run("scripts/seed_credit_bureau_demo.py")
    MARKER.write_text(
        json.dumps(
            {
                "status": "initialized",
                "model_architecture": "ONE_UNIFIED_GENERATIVE_AI",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Server initialization complete: {MARKER}")


if __name__ == "__main__":
    main()
