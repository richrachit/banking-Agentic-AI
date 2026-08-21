"""Download the optional unified local instruction model."""
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Download the unified local generative-AI model")
    parser.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--output", default="models/qwen2.5-1.5b-instruct")
    args = parser.parse_args()
    try:
        from huggingface_hub import snapshot_download
    except ImportError as error:
        raise SystemExit("Install dependencies first: pip install -r requirements-ai.txt") from error
    snapshot_download(repo_id=args.model, local_dir=Path(args.output))
    print(f"Model downloaded to {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
