#!/usr/bin/env python3
"""
Beginner-friendly pytest runner for LLM-TradeBot.

Default behavior:
- runs `pytest -q tests`
- disables third-party pytest auto plugins to avoid environment pollution
"""

import argparse
import os
import sys

import pytest


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LLM-TradeBot tests safely")
    parser.add_argument(
        "--no-plugin-isolation",
        action="store_true",
        help="Do not set PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
    )
    parser.add_argument(
        "pytest_args",
        nargs="*",
        help="Optional pytest args. Defaults to: -q tests",
    )
    args = parser.parse_args()

    if not args.no_plugin_isolation:
        os.environ.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")

    pytest_args = args.pytest_args if args.pytest_args else ["-q", "tests"]
    print("Running pytest:", " ".join(pytest_args))
    return pytest.main(pytest_args)


if __name__ == "__main__":
    raise SystemExit(main())
