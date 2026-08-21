from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .audit import AuditLog
from .automation_agent import OperationsAutomationAgent
from .dormancy_agent import DormancyAgent
from .policy import PolicyConfig
from .repository import LocalRepository

DATA = Path.cwd() / "data"


def main() -> None:
    parser = argparse.ArgumentParser(description="Bank-statement verification and dormant-account lifecycle")
    sub = parser.add_subparsers(dest="command", required=True)
    cycle = sub.add_parser("dormancy-cycle"); cycle.add_argument("--as-of", required=True)
    args = parser.parse_args()
    repository = LocalRepository(DATA / "state.json"); audit = AuditLog(DATA / "audit.jsonl")
    dormancy = DormancyAgent(repository, audit, PolicyConfig.from_data_directory(DATA), DATA / "dormancy_cases.sqlite3")
    if args.command == "dormancy-cycle":
        result = OperationsAutomationAgent(repository, audit, dormancy).run_cycle(date.fromisoformat(args.as_of))
        print(json.dumps(result.__dict__, indent=2))
