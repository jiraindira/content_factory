from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.env import load_env
from pipeline.tpw_auto_planner import TpwAutoPlanner, AutoFormatId


load_env()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Auto-plan and write a TPW post by generating a manual-style "
            "post_input.json and running the manual post writer."
        )
    )
    p.add_argument("--date", default=None, help="Logical post date (YYYY-MM-DD). Defaults to today().")
    p.add_argument("--input", default="data/inputs/manual/post_input.json", help="Where to write post_input.json")
    p.add_argument("--format", choices=["top_picks", "buyer_guide", "thought_leadership"], default=None,
                   help="Optional format override; otherwise rotation is used.")
    p.add_argument("--dry-run", action="store_true", help="Plan + generate but do not write the final post file.")
    p.add_argument("--debug-dir", default=None, help="Optional directory for debug artefacts from the writer.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    post_date = args.date or date.today().isoformat()

    format_override: AutoFormatId | None = args.format  # type: ignore[assignment]

    print("🟢 write_tpw_auto_post")
    print(f"📅 Date: {post_date}")
    print(f"📄 Input JSON path: {args.input}")
    if format_override:
        print(f"📐 Format override: {format_override}")
    print(f"🧪 Dry run: {args.dry_run}")
    if args.debug_dir:
        print(f"🧾 Debug artefacts: {args.debug_dir}")

    planner = TpwAutoPlanner()
    result = planner.run(
        current_date=post_date,
        input_path=str(args.input),
        format_override=format_override,
        run_writer=True,
        post_date=post_date,
        dry_run=bool(args.dry_run),
        debug_dir=str(args.debug_dir) if args.debug_dir else None,
    )

    print(
        "✅ TPW auto post complete: "
        f"topic='{result.topic.topic}' category={result.topic.category} "
        f"format={result.format_id} products={result.products_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
