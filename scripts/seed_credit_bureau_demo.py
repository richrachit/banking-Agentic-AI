from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from banking_agents.credit_bureau_agent import LocalCreditBureauDatabase  # noqa: E402


def main() -> None:
    database = LocalCreditBureauDatabase(ROOT / "data" / "credit_bureau.sqlite3")
    fixtures = [
        ("DEMOA0001A", 790, "LOCAL-HIGH-001"),
        ("DEMOB0002B", 710, "LOCAL-REVIEW-002"),
        ("DEMOC0003C", 580, "LOCAL-LOW-003"),
        ("DEMOD0004D", None, "LOCAL-NH-004"),
    ]
    for pan, score, reference in fixtures:
        database.seed_fixture(pan, score, reference)
    print(json.dumps({"database": str(database.db_path.resolve()), "fictional_fixtures": len(fixtures)}, indent=2))


if __name__ == "__main__":
    main()
