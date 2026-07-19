from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from banking_agents.local_models import MODEL_COMPONENTS  # noqa: E402
from banking_agents.training_store import ModelTrainingDatabase  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Show the local AI component, data, and model registry")
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "model_training.sqlite3")
    args = parser.parse_args()
    database = ModelTrainingDatabase(args.db)
    database.sync_catalog(MODEL_COMPONENTS)
    print(json.dumps(database.status_report(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
