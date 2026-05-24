#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path


def _bootstrap_python() -> None:
    try:
        import pymysql  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    if os.environ.get("DATA_AGENT_PYTHON_BOOTSTRAPPED") == "1":
        return

    candidates = [
        "/usr/local/opt/python@3.10/bin/python3.10",
        "/usr/local/bin/python3.10",
    ]
    for candidate in candidates:
        if Path(candidate).exists() and sys.executable != candidate:
            os.environ["DATA_AGENT_PYTHON_BOOTSTRAPPED"] = "1"
            os.execv(candidate, [candidate, *sys.argv])


_bootstrap_python()

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agent.executor import execute_query  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description="FinDataPilot CLI")
    parser.add_argument("--query", "-q", required=True, help="Natural-language financial query")
    parser.add_argument("--page", default="1", help="Page number")
    parser.add_argument("--limit", default="100", help="Rows per page")
    parser.add_argument("--no-save", action="store_true", help="Do not write files or MySQL trace rows")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = execute_query(
        query=args.query,
        page=args.page,
        limit=args.limit,
        save=not args.no_save,
    )
    print(json.dumps(result.payload, ensure_ascii=False, indent=2))
    return 0 if result.status_code < 400 else 1


if __name__ == "__main__":
    raise SystemExit(main())
