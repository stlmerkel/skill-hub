# skill_hub/cli.py
"""Command-line entry point: `skill-hub qa` and `skill-hub new-skill`."""

import argparse
import sys
from pathlib import Path

from skill_hub.qa import format_report, run_qa
from skill_hub.releases import RELEASE_CONFIG
from skill_hub.scaffold import ScaffoldError, create_skill


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skill-hub", description="Tools for running a skill hub.")
    commands = parser.add_subparsers(dest="command", required=True)
    qa = commands.add_parser("qa", help="validate hub.yml and every skill under src/")
    qa.add_argument("--root", type=Path, default=Path("."), help="hub root containing hub.yml and src/ (default: .)")
    qa.add_argument("--strict", action="store_true", help="treat warnings as errors")
    new_skill = commands.add_parser("new-skill", help="create a skill under src/ that passes QA")
    new_skill.add_argument("name", help="the skill's name: a-z, 0-9 and single hyphens")
    new_skill.add_argument("--root", type=Path, default=Path("."), help="hub root containing hub.yml (default: .)")
    args = parser.parse_args(argv)

    if args.command == "new-skill":
        try:
            created = create_skill(args.root, args.name)
        except ScaffoldError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"Created {created.path}")
        if not created.registered:
            print(f"Release registration skipped: no {RELEASE_CONFIG}")
        print("Next: replace the placeholder description and instructions, then run `uv run skill-hub qa`.")
        return 0

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")  # undecodable filenames must not crash the report
    result = run_qa(args.root)
    print(format_report(result))
    failed = bool(result.errors) or (args.strict and bool(result.warnings))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
