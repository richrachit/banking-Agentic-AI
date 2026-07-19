from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from banking_agents.local_models import LocalTrainingDataCollector  # noqa: E402
from banking_agents.repository import LocalRepository  # noqa: E402
from banking_agents.training_store import ModelTrainingDatabase  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the de-identified local AI training database")
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "model_training.sqlite3")
    parser.add_argument("--state", type=Path, default=ROOT / "data" / "state.json")
    parser.add_argument("--exception-db", type=Path, default=ROOT / "data" / "loan_exception_cases.sqlite3")
    parser.add_argument(
        "--include-synthetic-demo",
        action="store_true",
        help="Add clearly labelled positive/negative demo examples. They are not production evidence.",
    )
    args = parser.parse_args()
    database = ModelTrainingDatabase(args.db)
    collector = LocalTrainingDataCollector(LocalRepository(args.state), database, args.exception_db)
    print(json.dumps(collector.collect(include_synthetic_demo=args.include_synthetic_demo), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
