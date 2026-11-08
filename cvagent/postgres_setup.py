"""Initialize LangGraph checkpoint tables for local PostgreSQL."""

from __future__ import annotations

import argparse
import os

from .persistence import setup_postgres


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize CVAgent LangGraph PostgreSQL tables")
    parser.add_argument(
        "--url",
        default=os.environ.get("CVAGENT_POSTGRES_URL"),
        help="PostgreSQL URL (defaults to CVAGENT_POSTGRES_URL)",
    )
    args = parser.parse_args()
    if not args.url:
        parser.error("--url or CVAGENT_POSTGRES_URL is required")
    setup_postgres(args.url)
    print("LangGraph PostgreSQL checkpoint tables are ready.")


if __name__ == "__main__":
    main()
