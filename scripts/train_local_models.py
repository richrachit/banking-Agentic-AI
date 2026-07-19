from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from banking_agents.local_models import LocalAdvisoryModelTrainer  # noqa: E402
from banking_agents.training_store import ModelTrainingDatabase  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Train hash-registered local advisory models")
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "model_training.sqlite3")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "models")
    parser.add_argument(
        "--allow-synthetic-demo",
        action="store_true",
        help="Permit demo training when the local database lacks sufficient human-verified labels.",
    )
    args = parser.parse_args()
    trainer = LocalAdvisoryModelTrainer(ModelTrainingDatabase(args.db), args.output)
    print(json.dumps(trainer.train_all(allow_synthetic_demo=args.allow_synthetic_demo), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
