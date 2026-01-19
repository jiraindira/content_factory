from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

RegionId = Literal["UK"]


class AffiliateProviderConfig(BaseModel):
    label: str
    categories: List[str] = Field(default_factory=list)
    requires_signal_group: Optional[str] = None


class AffiliatesConfig(BaseModel):
    default_provider: str = Field(..., description="Provider id used as default fallback")
    region: RegionId = "UK"
    providers: Dict[str, AffiliateProviderConfig] = Field(default_factory=dict)
    signal_groups: Dict[str, List[str]] = Field(default_factory=dict)

    def provider_ids(self) -> list[str]:
        return list(self.providers.keys())
