from __future__ import annotations

"""Export the FastAPI contract for offline review and client generation."""

import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from banking_agents.api_app import create_app  # noqa: E402


def main() -> None:
    output_path = PROJECT_ROOT / "docs" / "openapi.json"
    schema = create_app(PROJECT_ROOT / "data").openapi()
    output_path.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Exported {output_path}")


if __name__ == "__main__":
    main()
