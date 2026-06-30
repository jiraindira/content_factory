"""
Daily content scheduler.
Run locally or via GitHub Actions cron.

For each client it checks:
  1. Is today one of their publish days?
  2. Are there approved topics still to produce?
  3. Is there already something pending review (don't pile up)?

If all three are clear it fires content generation.
"""
from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

BRANDS_DIR = Path(__file__).parent / "content_factory" / "brands"
TOPICS_DIR = Path(__file__).parent / "content_factory" / "topics"
GENERATED_DIR = Path(__file__).parent / "content_factory" / "generated"

WEEKDAY_MAP = {0: "mon", 1: "tue", 2: "wed", 3: "thu", 4: "fri", 5: "sat", 6: "sun"}


def _slot_for_today(brand: dict) -> dict | None:
    today = WEEKDAY_MAP[date.today().weekday()]
    return next((s for s in brand.get("content_slots", []) if s.get("day") == today), None)


def _has_pending_review(brand_id: str) -> bool:
    d = GENERATED_DIR / brand_id
    if not d.exists():
        return False
    for p in d.glob("*.yaml"):
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        if data.get("status") == "pending_review":
            return True
    return False


def _has_approved_topics(brand_id: str) -> bool:
    path = TOPICS_DIR / f"{brand_id}.yaml"
    if not path.exists():
        return False
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if data.get("status") != "approved":
        return False
    return any(t.get("status") not in ("generated", "sent") for t in data.get("topics", []))


def _generate_with_retry(brand_id: str, slot_type: str, attempts: int = 3) -> dict:
    """Generate content, retrying transient failures with exponential backoff.

    The SDK already retries connection/429/5xx at the API call; this is a second
    layer around the whole pipeline so a blip anywhere recovers within one run.
    """
    from content_factory.content_runner import run_for_brand

    last_err: Exception | None = None
    for i in range(attempts):
        try:
            return run_for_brand(brand_id=brand_id, slot_type=slot_type)
        except Exception as e:  # noqa: BLE001 — transient API/network errors
            last_err = e
            if i < attempts - 1:
                wait = 5 * (2 ** i)  # 5s, 10s, 20s
                print(f"   attempt {i + 1}/{attempts} failed: {e} — retrying in {wait}s")
                time.sleep(wait)
    assert last_err is not None
    raise last_err


def run() -> int:
    today_name = WEEKDAY_MAP[date.today().weekday()]
    print(f"=== Content Scheduler — {date.today()} ({today_name}) ===\n")

    if not BRANDS_DIR.exists():
        print("No brands directory — nothing to do.")
        return 0

    brands = sorted(p.stem for p in BRANDS_DIR.glob("*.yaml"))
    print(f"Clients: {', '.join(brands) or 'none'}\n")

    generated = 0
    skipped = 0
    failures: list[dict] = []

    for brand_id in brands:
        brand = yaml.safe_load((BRANDS_DIR / f"{brand_id}.yaml").read_text(encoding="utf-8")) or {}
        client_name = brand.get("client_name") or brand_id

        if not brand.get("plan_confirmed"):
            print(f"[{client_name}] Plan not confirmed by client — skipping")
            skipped += 1
            continue

        slot = _slot_for_today(brand)
        if not slot:
            print(f"[{client_name}] Not scheduled today — skipping")
            skipped += 1
            continue

        if _has_pending_review(brand_id):
            print(f"[{client_name}] Content already pending review — skipping until approved")
            skipped += 1
            continue

        if not _has_approved_topics(brand_id):
            print(f"[{client_name}] No approved topics remaining — skipping")
            skipped += 1
            continue

        slot_type = slot.get("type", "long_blog")
        print(f"[{client_name}] Generating {slot_type}...")

        try:
            result = _generate_with_retry(brand_id, slot_type)
            status = result.get("status", "unknown")
            topic = result.get("topic", "")[:70]
            print(f"[{client_name}] ✓ {status} — {topic}")
            generated += 1
        except Exception as e:
            import traceback
            print(f"[{client_name}] ✗ ERROR after retries: {e}")
            traceback.print_exc()
            failures.append({
                "brand_id": brand_id,
                "client_name": client_name,
                "slot_type": slot_type,
                "error": str(e),
            })

    print(f"\n=== Done — generated: {generated}, skipped: {skipped}, failed: {len(failures)} ===")

    # A failure must never be silent again: alert the operator and fail the run.
    if failures:
        try:
            from content_factory.emailer import send_scheduler_alert_email
            send_scheduler_alert_email(failures=failures, run_date=str(date.today()))
            print(f"Alert email sent to operator for {len(failures)} failure(s).")
        except Exception as e:
            print(f"WARNING: could not send scheduler alert email: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(run())
