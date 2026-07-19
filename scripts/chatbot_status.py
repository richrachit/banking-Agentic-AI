from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from banking_agents.chatbot_training import LocalChatbotTrainingDatabase  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Show local chatbot training status")
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "chatbot_training.sqlite3")
    args = parser.parse_args()
    print(json.dumps(LocalChatbotTrainingDatabase(args.db).status_report(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
