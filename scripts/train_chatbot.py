from __future__ import annotations

"""Seed and train the local Banking Support Chatbot intent model."""

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from banking_agents.chatbot_training import LocalChatbotIntentTrainer, LocalChatbotTrainingDatabase  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the local Banking Support Chatbot intent classifier")
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "chatbot_training.sqlite3")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "models")
    args = parser.parse_args()
    database = LocalChatbotTrainingDatabase(args.db)
    result = LocalChatbotIntentTrainer(database, args.output).train()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
