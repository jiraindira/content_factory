from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict

import httpx


@dataclass(frozen=True)
class InstagramConfig:
    """Configuration for Instagram Graph API posting.

    This client assumes you already have:
      - An Instagram Business/Creator account connected to a Facebook Page.
      - A Meta app with the appropriate instagram_basic / instagram_content_publish scopes.
      - A long-lived user access token with permissions to post.

    Images must be publicly reachable via HTTPS; the API cannot accept raw
    local files, so the caller is responsible for hosting the image and
    passing its URL.
    """

    user_id: str
    access_token: str
    api_base: str = "https://graph.facebook.com/v19.0"


class InstagramClient:
    def __init__(self, *, config: InstagramConfig | None = None) -> None:
        if config is None:
            user_id = (os.environ.get("INSTAGRAM_USER_ID") or "").strip()
            token = (os.environ.get("INSTAGRAM_ACCESS_TOKEN") or "").strip()
            api_base = (os.environ.get("INSTAGRAM_API_BASE") or "https://graph.facebook.com/v19.0").strip()
            if not user_id or not token:
                raise ValueError(
                    "INSTAGRAM_USER_ID and INSTAGRAM_ACCESS_TOKEN must be set in the environment "
                    "to enable automatic posting."
                )
            config = InstagramConfig(user_id=user_id, access_token=token, api_base=api_base)
        self._cfg = config

    @property
    def config(self) -> InstagramConfig:
        return self._cfg

    def create_photo_post(self, *, image_url: str, caption: str) -> Dict[str, Any]:
        """Create and publish a single-image Instagram post.

        The caller must ensure image_url is a publicly accessible HTTPS URL.
        Returns the JSON response from the final media_publish call.
        """

        image_url = (image_url or "").strip()
        if not image_url:
            raise ValueError("image_url must not be empty")

        caption = (caption or "").strip()

        with httpx.Client(timeout=30.0) as client:
            # Step 1: create an upload container
            create_url = f"{self._cfg.api_base}/{self._cfg.user_id}/media"
            create_resp = client.post(
                create_url,
                data={
                    "image_url": image_url,
                    "caption": caption,
                    "access_token": self._cfg.access_token,
                },
            )
            create_resp.raise_for_status()
            data = create_resp.json()
            creation_id = data.get("id")
            if not creation_id:
                raise RuntimeError(f"Instagram media creation response missing id: {data}")

            # Step 2: publish the container
            publish_url = f"{self._cfg.api_base}/{self._cfg.user_id}/media_publish"
            publish_resp = client.post(
                publish_url,
                data={
                    "creation_id": creation_id,
                    "access_token": self._cfg.access_token,
                },
            )
            publish_resp.raise_for_status()
            return publish_resp.json()  # type: ignore[no-any-return]
