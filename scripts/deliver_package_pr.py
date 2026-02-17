from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from content_factory.pr_delivery import deliver_package_as_pr, ensure_managed_repo_checkout, has_gh_cli


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Deliver a Content Package v1 into a managed-site repo as a PR-ready branch"
    )

    p.add_argument("--package-dir", required=True, help="Path to packages/{brand_id}/{run_id}")
    p.add_argument(
        "--managed-repo-path",
        required=True,
        help="Local path to managed-site repo checkout (cloned if missing and --managed-repo-url is provided)",
    )
    p.add_argument("--managed-repo-url", required=False, help="Git URL used to clone managed repo if path missing")
    p.add_argument(
        "--managed-python",
        required=False,
        help="Python executable to run managed-site hydration (defaults to current interpreter)",
    )
    p.add_argument("--base-branch", default="main")
    p.add_argument("--branch", required=False, help="Branch name to create/update")

    p.add_argument("--no-overwrite", action="store_true")
    p.add_argument("--no-pick-images", action="store_true")
    p.add_argument("--regen-hero", action="store_true", help="Attempt hero regen if OPENAI_API_KEY is set")

    p.add_argument("--commit", action="store_true", help="Create a git commit (stages changes first)")
    p.add_argument("--push", action="store_true", help="Push branch to origin (requires --commit)")
    p.add_argument(
        "--open-pr",
        action="store_true",
        help="Open a PR using GitHub CLI (gh). Prints instructions if gh is missing.",
    )

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    package_dir = Path(args.package_dir).resolve()
    managed_repo_path = Path(args.managed_repo_path).resolve()

    managed_repo_path = ensure_managed_repo_checkout(
        checkout_path=managed_repo_path,
        managed_repo_url=args.managed_repo_url,
    )

    result = deliver_package_as_pr(
        package_dir=package_dir,
        managed_repo_path=managed_repo_path,
        base_branch=args.base_branch,
        branch_name=args.branch,
        overwrite=not args.no_overwrite,
        enrich_pick_images=not args.no_pick_images,
        regen_hero_if_possible=bool(args.regen_hero),
        commit=bool(args.commit),
        push=bool(args.push),
        managed_python=args.managed_python,
    )

    print(f"Managed repo: {result.managed_repo_path}")
    print(f"Branch: {result.branch_name}")
    print(f"Changed entries: {result.changed_files}")

    if args.open_pr:
        if not has_gh_cli():
            print("gh not found. To open a PR, install GitHub CLI and run:")
            print(f"  cd {result.managed_repo_path}")
            print(f"  gh pr create --base {args.base_branch} --head {result.branch_name} --fill")
            return 0

        subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--base",
                args.base_branch,
                "--head",
                result.branch_name,
                "--fill",
            ],
            cwd=str(result.managed_repo_path),
            check=False,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
