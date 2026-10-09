# skill_hub/cli.py
"""Command-line entry point: `skill-hub qa`."""

import argparse
import sys
from pathlib import Path

from skill_hub.qa import format_report, run_qa


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skill-hub", description="Tools for running a skill hub.")
    commands = parser.add_subparsers(dest="command", required=True)
    qa = commands.add_parser("qa", help="validate hub.yml and every skill under src/")
    qa.add_argument("--root", type=Path, default=Path("."), help="hub root containing hub.yml and src/ (default: .)")
    qa.add_argument("--strict", action="store_true", help="treat warnings as errors")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")  # undecodable filenames must not crash the report
    result = run_qa(args.root)
    print(format_report(result))
    failed = bool(result.errors) or (args.strict and bool(result.warnings))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
