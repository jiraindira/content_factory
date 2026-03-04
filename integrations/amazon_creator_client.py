from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any


@dataclass(frozen=True)
class AmazonCreatorProduct:
    """Normalized product record from the Amazon Creator API.

    This is the minimal set of fields the selector + planner need.
    """

    asin: str
    title: str
    url: str
    price: str | None
    rating: float | None
    reviews_count: int | None
    raw: dict[str, Any] | None = None


class AmazonCreatorClient:
    """Thin wrapper around the Amazon Creator API SDK.

    NOTE: This class intentionally does **not** implement the actual
    network calls yet. It defines the contract and env configuration
    points so you can plug in the official SDK without changing the
    rest of the pipeline.
    """

    def __init__(
        self,
        *,
        partner_tag: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        marketplace: str = "amazon.co.uk",
    ) -> None:
        self.partner_tag = partner_tag or os.getenv("AMAZON_CREATOR_PARTNER_TAG", "").strip()
        self.client_id = client_id or os.getenv("AMAZON_CREATOR_CLIENT_ID", "").strip()
        self.client_secret = client_secret or os.getenv("AMAZON_CREATOR_CLIENT_SECRET", "").strip()
        self.marketplace = marketplace
        # Default to CreatorsAPI version 3.2 if not explicitly configured.
        self.version = os.getenv("AMAZON_CREATOR_VERSION", "3.2").strip() or "3.2"

        if not self.partner_tag:
            raise RuntimeError("Missing AMAZON_CREATOR_PARTNER_TAG env var for Amazon Creator API")

        if not self.client_id or not self.client_secret:
            raise RuntimeError("Missing AMAZON_CREATOR_CLIENT_ID/AMAZON_CREATOR_CLIENT_SECRET env vars")

        # TODO: Initialize the real Creator API SDK client here once
        # you have the Python bindings available, for example:
        # from creatorsapi_python_sdk.api_client import ApiClient
        # self._sdk_client = ApiClient(
        #     credential_id=self.client_id,
        #     credential_secret=self.client_secret,
        #     version=self.version,
        # )
        self._sdk_client: Any | None = None

    def search_products(
        self,
        *,
        query: str,
        max_results: int = 10,
    ) -> list[AmazonCreatorProduct]:
        """Search for products via the Creator API.

        This method **must** be implemented using the official
        Amazon Creator API SDK. It should:
        - execute a keyword search in the configured marketplace
        - limit to `max_results` items
        - return a list of AmazonCreatorProduct with:
          asin, title, url (affiliate link), price, rating, reviews_count.
        """

        raise NotImplementedError(
            "AmazonCreatorClient.search_products is not implemented. "
            "Wire this up to the official Creator API SDK when ready."
        )
