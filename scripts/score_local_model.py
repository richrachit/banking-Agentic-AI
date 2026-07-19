from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from banking_agents.local_models import LocalAdvisoryModelRuntime  # noqa: E402
from banking_agents.repository import LocalRepository  # noqa: E402
from banking_agents.training_store import ModelTrainingDatabase  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Score one loan with the local advisory model")
    parser.add_argument("--application-id", required=True)
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "model_training.sqlite3")
    parser.add_argument("--state", type=Path, default=ROOT / "data" / "state.json")
    parser.add_argument("--models", type=Path, default=ROOT / "data" / "models")
    args = parser.parse_args()
    loan = LocalRepository(args.state).get_loan(args.application_id)
    runtime = LocalAdvisoryModelRuntime(ModelTrainingDatabase(args.db), args.models)
    print(json.dumps(runtime.as_dict(runtime.score_loan(loan)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
