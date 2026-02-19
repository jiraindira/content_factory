from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from content_factory.adapters.dispatch import render_for_request, write_delivery
from content_factory.artifact_io import write_content_artifact
from content_factory.artifact_validation import validate_artifact_against_specs
from content_factory.brand_context import (
    artifact_path_for_brand,
    build_brand_context_artifact,
    write_brand_context_artifact,
)
from content_factory.compiler import compile_content_artifact
from content_factory.channel_qa import validate_artifact_against_channel_specs
from content_factory.generation import generate_filled_artifact
from content_factory.onboarding import write_onboarding_files
from content_factory.validation import load_brand_profile, load_content_request, validate_request_against_brand


def _run_request_pipeline(
    *,
    repo_root: Path,
    brand_path: Path,
    request_path: Path | None,
    brand,
    req,
    run_id: str,
    build_context_if_missing: bool,
    write_package: bool,
) -> int:
    ctx_path = artifact_path_for_brand(repo_root=repo_root, brand_id=brand.brand_id)
    if not ctx_path.exists() and build_context_if_missing:
        artifact = build_brand_context_artifact(brand=brand, repo_root=repo_root)
        ctx_path = write_brand_context_artifact(repo_root=repo_root, artifact=artifact)

    if not ctx_path.exists():
        raise FileNotFoundError(
            f"BrandContextArtifact not found: {ctx_path}. Run `content-factory build-context --brand ...` first."
        )

    from content_factory.brand_context import BrandContextArtifact

    ctx = BrandContextArtifact.model_validate_json(ctx_path.read_text(encoding="utf-8"))
    artifact = compile_content_artifact(brand=brand, request=req, brand_context=ctx, run_id=run_id)

    # Populate content deterministically via intent/form-specific generation.
    _ = generate_filled_artifact(brand=brand, request=req, artifact=artifact)

    # Optional body-only editorial pass (LLM). Non-blocking by design.
    try:
        from content_factory.editorial import apply_copy_editor_to_artifact_if_applicable

        _ = apply_copy_editor_to_artifact_if_applicable(brand=brand, request=req, artifact=artifact)
    except Exception:
        pass

    validate_artifact_against_specs(brand=brand, request=req, artifact=artifact)
    validate_artifact_against_channel_specs(brand=brand, request=req, artifact=artifact)

    out_artifact_path = write_content_artifact(repo_root=repo_root, artifact=artifact)
    delivery = render_for_request(brand=brand, request=req, artifact=artifact)
    out_delivery_path = write_delivery(repo_root=repo_root, delivery=delivery)

    if write_package:
        if req.delivery_target.channel.value != "blog_article":
            raise ValueError("--write-package is currently supported only for blog_article deliveries")

        from content_factory.adapters.common import extract_topic_from_artifact
        from content_factory.package_writer import write_content_package_v1

        topic = extract_topic_from_artifact(artifact) or artifact.run_id
        pkg = write_content_package_v1(
            repo_root=repo_root,
            brand_id=brand.brand_id,
            run_id=run_id,
            publish_date=req.publish.publish_date,
            slug_source=topic,
            post_markdown=delivery.content,
        )
        print(f"Wrote Content Package: {pkg.package_dir}")

    if request_path is not None:
        print(f"Request: {request_path}")
    if brand_path is not None:
        print(f"Brand: {brand_path}")
    print(f"Wrote ContentArtifact: {out_artifact_path}")
    print(f"Wrote Delivery Output: {out_delivery_path}")
    return 0


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _abs_from_repo(repo_root: Path, p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else (repo_root / path)


def cmd_onboard(args: argparse.Namespace) -> int:
    repo_root = _repo_root()
    publish_date = date.fromisoformat(args.publish_date) if args.publish_date else date.today()

    paths = write_onboarding_files(
        repo_root=repo_root,
        brand_id=args.brand_id,
        domains_supported=args.domains_supported.split(","),
        domain_primary=args.domain_primary,
        publish_date=publish_date,
    )

    print(f"Wrote brand: {paths.brand_path}")
    print(f"Wrote request: {paths.request_path}")
    print("Next: edit the allowlist, policies, and sources; then validate.")
    return 0


def cmd_validate_brand(args: argparse.Namespace) -> int:
    repo_root = _repo_root()
    brand_path = _abs_from_repo(repo_root, args.brand)
    _ = load_brand_profile(brand_path)
    print(f"OK: brand file valid: {brand_path}")
    return 0


def cmd_validate_request(args: argparse.Namespace) -> int:
    repo_root = _repo_root()
    brand_path = _abs_from_repo(repo_root, args.brand)
    request_path = _abs_from_repo(repo_root, args.request)

    brand = load_brand_profile(brand_path)
    req = load_content_request(request_path)
    validate_request_against_brand(brand=brand, request=req)
    print(f"OK: request valid against brand: {request_path}")
    return 0


def cmd_build_context(args: argparse.Namespace) -> int:
    repo_root = _repo_root()
    brand_path = _abs_from_repo(repo_root, args.brand)
    brand = load_brand_profile(brand_path)

    artifact = build_brand_context_artifact(brand=brand, repo_root=repo_root)
    out_path = write_brand_context_artifact(repo_root=repo_root, artifact=artifact)
    print(f"Wrote BrandContextArtifact: {out_path}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    repo_root = _repo_root()
    brand_path = _abs_from_repo(repo_root, args.brand)
    request_path = _abs_from_repo(repo_root, args.request)

    brand = load_brand_profile(brand_path)
    req = load_content_request(request_path)
    validate_request_against_brand(brand=brand, request=req)

    run_id = args.run_id or request_path.stem
    return _run_request_pipeline(
        repo_root=repo_root,
        brand_path=brand_path,
        request_path=request_path,
        brand=brand,
        req=req,
        run_id=run_id,
        build_context_if_missing=bool(args.build_context_if_missing),
        write_package=bool(args.write_package),
    )


def cmd_import_manual(args: argparse.Namespace) -> int:
    repo_root = _repo_root()
    brand_path = _abs_from_repo(repo_root, args.brand)
    input_path = _abs_from_repo(repo_root, args.input)

    brand = load_brand_profile(brand_path)

    from content_factory.manual_import import legacy_manual_to_request, load_legacy_manual_post_input

    legacy = load_legacy_manual_post_input(input_path)
    publish_date = date.fromisoformat(args.publish_date) if args.publish_date else date.today()
    run_id = args.run_id or input_path.stem

    result = legacy_manual_to_request(brand=brand, legacy=legacy, publish_date=publish_date, run_id=run_id)
    req = result.request
    validate_request_against_brand(brand=brand, request=req)

    if args.request_out:
        out_request_path = _abs_from_repo(repo_root, args.request_out)
        out_request_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = repo_root / "content_factory" / "outputs" / "imported_requests"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_request_path = out_dir / f"{run_id}.yaml"

    import yaml

    out_request_path.write_text(yaml.safe_dump(req.to_dict(), sort_keys=False), encoding="utf-8")
    print(f"Wrote imported request: {out_request_path}")
    for w in result.warnings:
        print(f"WARN: {w}")

    return _run_request_pipeline(
        repo_root=repo_root,
        brand_path=brand_path,
        request_path=out_request_path,
        brand=brand,
        req=req,
        run_id=run_id,
        build_context_if_missing=bool(args.build_context_if_missing),
        write_package=bool(args.write_package),
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="content-factory", description="AI Content Factory CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    onboard = sub.add_parser("onboard", help="Scaffold brand + request YAML for a new client")
    onboard.add_argument("--brand-id", required=True)
    onboard.add_argument("--domains-supported", required=True, help="Comma-separated domains (e.g. leadership,tech)")
    onboard.add_argument("--domain-primary", required=True)
    onboard.add_argument("--publish-date", required=False, help="YYYY-MM-DD (defaults to today)")
    onboard.set_defaults(func=cmd_onboard)

    vb = sub.add_parser("validate-brand", help="Validate a brand YAML")
    vb.add_argument("--brand", required=True)
    vb.set_defaults(func=cmd_validate_brand)

    vr = sub.add_parser("validate-request", help="Validate a request YAML against a brand")
    vr.add_argument("--brand", required=True)
    vr.add_argument("--request", required=True)
    vr.set_defaults(func=cmd_validate_request)

    bc = sub.add_parser("build-context", help="Build BrandContextArtifact JSON (robots enforced)")
    bc.add_argument("--brand", required=True)
    bc.set_defaults(func=cmd_build_context)

    run = sub.add_parser("run", help="Compile a ContentArtifact + delivery output")
    run.add_argument("--brand", required=True)
    run.add_argument("--request", required=True)
    run.add_argument("--run-id", required=False)
    run.add_argument(
        "--build-context-if-missing",
        action="store_true",
        help="If BrandContextArtifact is missing, build it first.",
    )
    run.add_argument(
        "--write-package",
        action="store_true",
        help="Write Content Package v1 into content_factory/packages/{brand_id}/{run_id}",
    )
    run.set_defaults(func=cmd_run)

    imp = sub.add_parser(
        "import-manual",
        help="Import legacy manual post_input.json into a factory request and run the pipeline",
    )
    imp.add_argument("--brand", required=True)
    imp.add_argument("--input", required=True, help="Path to legacy manual post_input.json")
    imp.add_argument("--publish-date", required=False, help="YYYY-MM-DD (defaults to today)")
    imp.add_argument("--run-id", required=False, help="Defaults to input filename stem")
    imp.add_argument(
        "--request-out",
        required=False,
        help="Optional path to write the generated request YAML (defaults to content_factory/outputs/imported_requests/{run_id}.yaml)",
    )
    imp.add_argument(
        "--build-context-if-missing",
        action="store_true",
        help="If BrandContextArtifact is missing, build it first.",
    )
    imp.add_argument(
        "--write-package",
        action="store_true",
        help="Write Content Package v1 into content_factory/packages/{brand_id}/{run_id}",
    )
    imp.set_defaults(func=cmd_import_manual)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
