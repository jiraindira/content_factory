from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
from typing import Any, Literal

from agents.topic_agent import TopicSelectionAgent
from agents.product_agent import ProductDiscoveryAgent
from pipeline.manual_post_writer import ManualPostWriter
from pipeline.amazon_product_selector import AmazonProductSelector

from schemas.topic import TopicInput, TopicOutput
from schemas.product import Product as DiscoveredProduct


AutoFormatId = Literal["top_picks", "buyer_guide", "thought_leadership"]


@dataclass(frozen=True)
class TpwAutoPlannerConfig:
    """Configuration for the TPW auto-planning pipeline.

    This is intentionally minimal – more knobs (e.g. per-format cadences,
    rating/review thresholds) can be added without breaking callers.
    """

    region: str = "GB"
    default_input_path: Path = Path("data/inputs/manual/post_input.json")
    max_products_top_picks: int = 10
    max_products_thought_leadership: int = 3
    min_products: int = 3
    format_history_path: Path = Path("memory/tpw_format_history.json")


@dataclass(frozen=True)
class TpwAutoPlannerResult:
    topic: TopicOutput
    format_id: AutoFormatId
    input_path: Path
    products_count: int


class TpwAutoPlanner:
    """End-to-end orchestrator for TPW auto-planned posts.

    Responsibilities (current implementation):
    - Pick a topic/category/audience using TopicSelectionAgent
    - Choose a post format with simple rotation across recent runs
    - Discover candidate products using ProductDiscoveryAgent
    - Convert candidates into a manual-style post_input.json compatible
      with ManualPostWriter
    - Optionally invoke ManualPostWriter to produce the Astro post

    NOTE: This version does *not* yet call the Amazon Product Advertising API.
    Product URLs are Amazon search-result URLs derived from the
    amazon_search_query/title so that the downstream pipeline has
    valid http(s) URLs. Rating/review counts are passed through from the
    discovery agent (typically null) and can be enriched later via a
    dedicated Amazon/catalog agent.
    """

    def __init__(
        self,
        *,
        config: TpwAutoPlannerConfig | None = None,
        logger=print,
    ) -> None:
        self.config = config or TpwAutoPlannerConfig()
        self._log = logger
        self._topic_agent = TopicSelectionAgent()
        self._product_agent = ProductDiscoveryAgent()
        self._amazon_selector = AmazonProductSelector(logger=logger)

    # ------------------
    # Public API
    # ------------------

    def run(
        self,
        *,
        current_date: str | None = None,
        input_path: str | None = None,
        format_override: AutoFormatId | None = None,
        run_writer: bool = False,
        post_date: str | None = None,
        dry_run: bool = False,
        debug_dir: str | None = None,
    ) -> TpwAutoPlannerResult:
        """Generate post_input.json (and optionally write the post).

        - current_date: logical "today" for topic selection (defaults to today())
        - input_path: where to write the post_input.json (defaults to config path)
        - format_override: force a specific format instead of rotation
        - run_writer: if True, immediately invoke ManualPostWriter
        - post_date: date used in output slug (defaults to today())
        - dry_run: passed through to ManualPostWriter (no filesystem writes)
        - debug_dir: optional debug artefacts dir for ManualPostWriter
        """

        today_str = current_date or date.today().isoformat()
        input_path_p = Path(input_path) if input_path else self.config.default_input_path

        topic = self._choose_topic(current_date=today_str)
        format_id = format_override or self._choose_format()
        products = self._discover_products(topic=topic, format_id=format_id, current_date=today_str)

        post_input = self._build_post_input(topic=topic, products=products)
        self._write_post_input(path=input_path_p, payload=post_input)

        self._log(
            f"🟢 TPW auto planner wrote input JSON: {input_path_p} "
            f"(format={format_id}, products={len(products)})"
        )

        if run_writer:
            writer = ManualPostWriter(logger=self._log)
            writer.run(
                input_path=str(input_path_p),
                post_date=post_date or today_str,
                dry_run=dry_run,
                debug_dir=debug_dir,
            )

        return TpwAutoPlannerResult(
            topic=topic,
            format_id=format_id,
            input_path=input_path_p,
            products_count=len(products),
        )

    # ------------------
    # Topic + format
    # ------------------

    def _choose_topic(self, *, current_date: str) -> TopicOutput:
        """Delegate to TopicSelectionAgent.

        Category rotation is handled by CategoryMemory within the agent.
        """

        inp = TopicInput(current_date=current_date, region=self.config.region)
        topic = self._topic_agent.run(inp)
        self._log(
            f"📌 Topic selected: category={topic.category} "
            f"topic='{topic.topic}' audience='{topic.audience}'"
        )
        return topic

    def _choose_format(self) -> AutoFormatId:
        """Pick a format with simple rotation across recent runs.

        This keeps a small JSON history file under memory/ and always
        chooses the least-used format among:
        ["top_picks", "buyer_guide", "thought_leadership"].
        """

        formats: list[AutoFormatId] = ["top_picks", "buyer_guide", "thought_leadership"]
        history = self._load_format_history()

        counts: dict[AutoFormatId, int] = {f: 0 for f in formats}
        for f in history:
            if f in counts:
                counts[f] += 1

        # Choose the least-used format; ties go to the earlier item in the list.
        chosen: AutoFormatId = min(formats, key=lambda f: counts.get(f, 0))

        history.append(chosen)
        # Keep only the last 50 entries to bound file size.
        if len(history) > 50:
            history = history[-50:]
        self._save_format_history(history)

        self._log(f"📐 Format selected: {chosen} (history={counts})")
        return chosen

    def _load_format_history(self) -> list[AutoFormatId]:
        path = self.config.format_history_path
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                return [f for f in raw if isinstance(f, str)]  # type: ignore[list-item]
        except Exception:
            # If anything goes wrong, start fresh but do not crash the run.
            return []
        return []

    def _save_format_history(self, history: list[AutoFormatId]) -> None:
        path = self.config.format_history_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(history, indent=2), encoding="utf-8")

    # ------------------
    # Product discovery + conversion
    # ------------------

    def _discover_products(
        self,
        *,
        topic: TopicOutput,
        format_id: AutoFormatId,
        current_date: str,
    ) -> list[DiscoveredProduct]:
        """Run ProductDiscoveryAgent to get ideas, then select via Amazon.

        The discovery agent proposes product ideas + search queries; the
        Amazon selector then calls the Creator API, enforces thresholds,
        and returns concrete Amazon products.
        """

        discovered = self._product_agent.run(topic)
        if not discovered:
            raise RuntimeError("ProductDiscoveryAgent returned no products")

        if format_id == "thought_leadership":
            desired = self.config.max_products_thought_leadership
        else:
            desired = self.config.max_products_top_picks

        queries = [p.amazon_search_query or p.title for p in discovered]

        selected = self._amazon_selector.select_for_topic(
            topic=topic,
            queries=queries,
            desired_count=desired,
            min_count=self.config.min_products,
            current_date=current_date,
        )

        self._log(
            f"🧺 Products discovered: {len(discovered)} ideas, "
            f"Amazon-selected={len(selected)}"
        )
        return selected

    def _build_post_input(
        self,
        *,
        topic: TopicOutput,
        products: list[Any],
    ) -> dict[str, Any]:
        """Convert topic + discovered products into post_input.json shape.

        Shape is compatible with ManualPostWriter (see write_manual_post.py):
          {
            "category": "...",
            "subcategory": "...",
            "audience": "...",
            "seed_title": "...",        # optional
            "seed_description": "...",  # optional
            "products": [
              {"title": "...", "url": "https://...", "price": "—", ...}
            ],
          }
        """

        # Single primary category for now; managed site taxonomy can map it.
        category = str(topic.category)
        audience = topic.audience

        seed_title = None  # Let FinalTitleAgent derive the final title
        seed_description = topic.rationale or topic.search_intent or ""

        products_out: list[dict[str, Any]] = []
        for p in products:
            title = getattr(p, "title", "")
            url = getattr(p, "url", "")
            price = getattr(p, "price", None)
            rating = getattr(p, "rating", None)
            reviews_count = getattr(p, "reviews_count", None)

            products_out.append(
                {
                    "title": title,
                    "url": url,
                    "price": price or "—",
                    "rating": rating,
                    "reviews_count": reviews_count,
                    "description": getattr(p, "description", ""),
                }
            )

        return {
            "category": category,
            "subcategory": "",  # can be refined later if needed
            "audience": audience,
            "seed_title": seed_title,
            "seed_description": seed_description,
            "products": products_out,
        }

    # ------------------
    # IO helpers
    # ------------------

    def _write_post_input(self, *, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, indent=2, ensure_ascii=False)
        path.write_text(text, encoding="utf-8")
