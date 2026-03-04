from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
from typing import Iterable

from integrations.amazon_creator_client import AmazonCreatorClient, AmazonCreatorProduct
from schemas.topic import TopicOutput
from lib.product_catalog import ProductCatalog, CatalogItem


@dataclass(frozen=True)
class AmazonSelectorConfig:
    primary_min_rating: float = 4.3
    primary_min_reviews: int = 2000
    fallback_min_rating: float = 4.0
    fallback_min_reviews: int = 1000
    history_path: Path = Path("memory/tpw_asin_history.json")
    history_window_posts: int = 20
    provider_id: str = "amazon_uk"
    catalog_path: Path = Path("data/catalog/master.json")


class AmazonProductSelector:
    """Selects Amazon products for a TPW topic using the Creator API.

    Responsibilities:
    - Call AmazonCreatorClient.search_products() for a set of queries
    - Enforce rating/review thresholds with a fallback band
    - Avoid reusing ASINs seen in the last N posts unless necessary
    - Upsert catalog entries with the chosen products' facts
    """

    def __init__(
        self,
        *,
        client: AmazonCreatorClient | None = None,
        config: AmazonSelectorConfig | None = None,
        logger=print,
    ) -> None:
        self._client = client or AmazonCreatorClient()
        self._config = config or AmazonSelectorConfig()
        self._log = logger

    def select_for_topic(
        self,
        *,
        topic: TopicOutput,
        queries: Iterable[str],
        desired_count: int,
        min_count: int,
        current_date: str | None = None,
    ) -> list[AmazonCreatorProduct]:
        today = current_date or date.today().isoformat()

        queries_list = [q for q in (q.strip() for q in queries) if q]
        if not queries_list:
            queries_list = [topic.topic]

        candidates: list[AmazonCreatorProduct] = []
        seen_asins: set[str] = set()

        for q in queries_list:
            products = self._client.search_products(query=q, max_results=desired_count * 2)
            for p in products:
                asin = (p.asin or "").strip()
                if not asin or asin in seen_asins:
                    continue
                seen_asins.add(asin)
                candidates.append(p)

        if not candidates:
            raise RuntimeError("Amazon Creator API returned no candidate products for the topic")

        recent_asins = self._load_recent_asins()

        selected = self._filter_with_thresholds(
            candidates=candidates,
            min_rating=self._config.primary_min_rating,
            min_reviews=self._config.primary_min_reviews,
            desired_count=desired_count,
            min_count=min_count,
            recent_asins=recent_asins,
        )

        if len(selected) < min_count:
            selected = self._filter_with_thresholds(
                candidates=candidates,
                min_rating=self._config.fallback_min_rating,
                min_reviews=self._config.fallback_min_reviews,
                desired_count=desired_count,
                min_count=min_count,
                recent_asins=recent_asins,
            )

        if len(selected) < min_count:
            raise RuntimeError(
                "Unable to find enough products meeting rating/review thresholds "
                f"(needed at least {min_count}, found {len(selected)})."
            )

        self._log(
            f"🛒 Amazon selector chose {len(selected)} products "
            f"(desired={desired_count}, min={min_count})"
        )

        self._update_history(asins=[p.asin for p in selected], current_date=today)
        self._upsert_catalog(products=selected)
        return selected[:desired_count]

    # ------------------
    # Internal helpers
    # ------------------

    def _filter_with_thresholds(
        self,
        *,
        candidates: list[AmazonCreatorProduct],
        min_rating: float,
        min_reviews: int,
        desired_count: int,
        min_count: int,
        recent_asins: set[str],
    ) -> list[AmazonCreatorProduct]:
        def meets(p: AmazonCreatorProduct) -> bool:
            rating = p.rating or 0.0
            reviews = p.reviews_count or 0
            return rating >= min_rating and reviews >= min_reviews

        filtered = [p for p in candidates if meets(p)]
        if not filtered:
            return []

        # Prefer products not used recently.
        fresh = [p for p in filtered if p.asin not in recent_asins]
        reused = [p for p in filtered if p.asin in recent_asins]

        ordered: list[AmazonCreatorProduct] = []
        ordered.extend(fresh)
        for p in reused:
            if p.asin not in {x.asin for x in ordered}:
                ordered.append(p)

        if len(ordered) >= desired_count:
            return ordered[:desired_count]

        if len(ordered) >= min_count:
            return ordered[:max(min_count, len(ordered))]

        return ordered

    def _load_recent_asins(self) -> set[str]:
        path = self._config.history_path
        if not path.exists():
            return set()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                return set()
            # raw: [{"date": "...", "asins": ["..."]}, ...]
            entries = raw[-self._config.history_window_posts :]
            asins: set[str] = set()
            for it in entries:
                if not isinstance(it, dict):
                    continue
                vals = it.get("asins")
                if isinstance(vals, list):
                    for a in vals:
                        if isinstance(a, str) and a.strip():
                            asins.add(a.strip())
            return asins
        except Exception:
            return set()

    def _update_history(self, *, asins: list[str], current_date: str) -> None:
        path = self._config.history_path
        try:
            if path.exists():
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    history = raw
                else:
                    history = []
            else:
                history = []
        except Exception:
            history = []

        entry = {
            "date": current_date,
            "asins": [a for a in asins if isinstance(a, str) and a.strip()],
        }
        history.append(entry)
        if len(history) > self._config.history_window_posts:
            history = history[-self._config.history_window_posts :]

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")

    def _upsert_catalog(self, *, products: list[AmazonCreatorProduct]) -> None:
        catalog = ProductCatalog(path=self._config.catalog_path)
        for p in products:
            title = (p.title or "").strip()
            if not title:
                continue

            catalog_key = catalog.default_catalog_key(provider=self._config.provider_id, title=title)
            item: CatalogItem = {
                "provider": self._config.provider_id,
                "status": "ok",
                "title": title,
                "affiliate_url": p.url,
                "rating": float(p.rating or 0.0),
                "reviews_count": int(p.reviews_count or 0),
                "price": p.price or "",
                "asin": p.asin,
                "notes": "",
            }
            catalog.upsert_item(catalog_key=catalog_key, item=item)
