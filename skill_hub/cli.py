# skill_hub/cli.py
"""Command-line entry point: `skill-hub qa`, `skill-hub new-skill`, `skill-hub manifests`, `skill-hub build`
and `skill-hub deploy-config`."""

import argparse
import os
import sys
from pathlib import Path

from skill_hub.catalog import BuildError
from skill_hub.config import check_hub
from skill_hub.deploy import render_outputs
from skill_hub.manifests import MANIFEST_PATHS, ManifestError, render_manifests, write_manifests
from skill_hub.qa import format_report, run_qa
from skill_hub.releases import RELEASE_CONFIG
from skill_hub.scaffold import ScaffoldError, create_skill
from skill_hub.site import build_site


def _update_manifests(root: Path) -> int:
    """Regenerate both marketplace manifests and return the skill count. Raises ManifestError."""
    result = run_qa(root)
    blocking = len([f for f in result.errors if f.check_id != "R7"])
    if blocking:
        errors = "error" if blocking == 1 else "errors"
        raise ManifestError(f"QA found {blocking} {errors}; run `skill-hub qa` and fix them first")
    write_manifests(root, render_manifests(root, check_hub(root)[1]))
    return result.skill_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skill-hub", description="Tools for running a skill hub.")
    commands = parser.add_subparsers(dest="command", required=True)
    qa = commands.add_parser("qa", help="validate hub.yml and every skill under skills/")
    qa.add_argument("--root", type=Path, default=Path("."), help="hub root containing hub.yml and skills/ (default: .)")
    qa.add_argument("--strict", action="store_true", help="treat warnings as errors")
    new_skill = commands.add_parser("new-skill", help="create a skill under skills/ that passes QA")
    new_skill.add_argument("name", help="the skill's name: a-z, 0-9 and single hyphens")
    new_skill.add_argument("--root", type=Path, default=Path("."), help="hub root containing hub.yml (default: .)")
    manifests = commands.add_parser(
        "manifests", help="write the marketplace manifests that list each skill for Claude Code and Cursor"
    )
    manifests.add_argument("--root", type=Path, default=Path("."), help="hub root containing hub.yml (default: .)")
    build = commands.add_parser("build", help="build the marketplace page and catalog.json from hub.yml and skills/")
    build.add_argument(
        "--root", type=Path, default=Path("."), help="hub root containing hub.yml and skills/ (default: .)"
    )
    build.add_argument("--out", type=Path, default=Path("site"), help="output folder (default: site)")
    deploy_config = commands.add_parser(
        "deploy-config", help="print hub.yml's deploy target and its settings, as the deploy workflows read them"
    )
    deploy_config.add_argument("--root", type=Path, default=Path("."), help="hub root containing hub.yml (default: .)")
    deploy_config.add_argument(
        "--github-output", action="store_true", help="append to the file named by $GITHUB_OUTPUT instead of printing"
    )
    args = parser.parse_args(argv)

    if args.command == "deploy-config":
        config = check_hub(args.root)[1]
        if config is None:
            print("error: hub.yml has QA errors; run `skill-hub qa` and fix them first", file=sys.stderr)
            return 1
        text = render_outputs(config.deploy)
        if not args.github_output:
            print(text, end="")
            return 0
        output = os.environ.get("GITHUB_OUTPUT")
        if not output:
            print("error: GITHUB_OUTPUT is not set; --github-output only works inside GitHub Actions", file=sys.stderr)
            return 1
        with open(output, "a", encoding="utf-8") as file:
            file.write(text)
        target = config.deploy.target
        print(f"Deploy target: {target}" if target else "No deploy target set; the deploy jobs will be skipped")
        return 0

    if args.command == "build":
        try:
            result = build_site(args.root, args.out)
        except BuildError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        for warning in result.warnings:
            print(f"warning: {warning}")
        skills = "skill" if result.skill_count == 1 else "skills"
        print(f"Built the marketplace page for {result.skill_count} {skills} in {args.out}")
        return 0

    if args.command == "manifests":
        try:
            count = _update_manifests(args.root)
        except ManifestError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        skills = "skill" if count == 1 else "skills"
        print(f"Wrote {MANIFEST_PATHS[0]} and {MANIFEST_PATHS[1]} for {count} {skills}")
        return 0

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
        try:
            _update_manifests(args.root)
        except ManifestError:
            print("Manifests not updated: fix the QA errors, then run `skill-hub manifests`")
        else:
            print("Updated the marketplace manifests")
        return 0

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")  # undecodable filenames must not crash the report
    result = run_qa(args.root)
    print(format_report(result))
    failed = bool(result.errors) or (args.strict and bool(result.warnings))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
