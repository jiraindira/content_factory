from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Dict, List, Optional, Union

from pydantic import Field, model_validator

from schemas.base import SchemaBase


class BrandArchetype(str, Enum):
    trusted_guide = "trusted_guide"
    expert_reviewer = "expert_reviewer"
    enthusiastic_enthusiast = "enthusiastic_enthusiast"
    lifestyle_curator = "lifestyle_curator"


class ContentIntent(str, Enum):
    product_recommendation = "product_recommendation"
    product_education = "product_education"
    thought_leadership = "thought_leadership"
    opinion_pov = "opinion_pov"
    digest_curation = "digest_curation"


class ProductRecommendationForm(str, Enum):
    top_x_list = "top_x_list"
    in_depth_single_review = "in_depth_single_review"
    comparison_table = "comparison_table"
    buyer_guide = "buyer_guide"
    alternatives_roundup = "alternatives_roundup"


class ThoughtLeadershipForm(str, Enum):
    core_insight_essay = "core_insight_essay"
    framework_breakdown = "framework_breakdown"
    contrarian_take = "contrarian_take"
    myths_vs_reality = "myths_vs_reality"
    narrative_with_lesson = "narrative_with_lesson"
    micro_case_study = "micro_case_study"
    question_led_exploration = "question_led_exploration"


class Domain(str, Enum):
    leadership = "leadership"
    finance = "finance"
    health = "health"
    pets = "pets"
    home = "home"
    kitchen = "kitchen"
    tech = "tech"


class BrandSourceKind(str, Enum):
    url = "url"
    file = "file"


class BrandSourcePurpose(str, Enum):
    homepage = "homepage"
    linkedin_profile = "linkedin_profile"
    about_page = "about_page"
    services_page = "services_page"
    product_pages = "product_pages"
    policies = "policies"
    longform_content = "longform_content"
    other = "other"


class TopicMode(str, Enum):
    manual = "manual"
    auto = "auto"


class DisclaimerLocation(str, Enum):
    header = "header"
    footer = "footer"
    before_products = "before_products"


class Persona(str, Enum):
    practical_expert = "practical_expert"
    warm_reflective = "warm_reflective"
    quirky_fun = "quirky_fun"
    minimalist_direct = "minimalist_direct"
    deeply_technical = "deeply_technical"
    calm_authoritative = "calm_authoritative"
    direct_insight_dense = "direct_insight_dense"
    provocative_challenger = "provocative_challenger"
    minimalist_executive = "minimalist_executive"


class PersonaModifier(str, Enum):
    science_led_explainer = "science_led_explainer"
    reassuring = "reassuring"
    slightly_playful = "slightly_playful"
    none = "none"


class ScienceExplicitness(str, Enum):
    implied = "implied"
    explicit_when_credibility_helpful = "explicit_when_credibility_helpful"
    explicit_often = "explicit_often"


class PersonalPresence(str, Enum):
    none = "none"
    occasional_personal_anecdotes = "occasional_personal_anecdotes"
    frequent_personal_anecdotes = "frequent_personal_anecdotes"


class NarrationMode(str, Enum):
    third_person_only = "third_person_only"
    first_person_allowed = "first_person_allowed"
    first_person_preferred = "first_person_preferred"


class PrimaryAudience(str, Enum):
    senior_executives_c_suite = "senior_executives_c_suite"
    mid_level_leaders = "mid_level_leaders"
    founders_entrepreneurs = "founders_entrepreneurs"
    sales_leaders = "sales_leaders"
    professional_speakers = "professional_speakers"
    coaches_consultants = "coaches_consultants"
    general_consumers = "general_consumers"
    enthusiasts_hobbyists = "enthusiasts_hobbyists"


class AudienceSophistication(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class CommercialPosture(str, Enum):
    invisible = "invisible"
    soft_recommendation = "soft_recommendation"
    clear_recommendation = "clear_recommendation"
    explicit_cta = "explicit_cta"


class CTAPolicy(str, Enum):
    none = "none"
    soft_authority_signature_line = "soft_authority_signature_line"
    gentle_cta_at_end = "gentle_cta_at_end"
    clear_invitation = "clear_invitation"


class ProhibitedBehavior(str, Enum):
    fake_scarcity = "fake_scarcity"
    hype_superlatives = "hype_superlatives"
    pressure_language = "pressure_language"


class ContentDepth(str, Enum):
    micro = "micro"
    short = "short"
    medium = "medium"
    long = "long"


class DeliveryChannel(str, Enum):
    blog_article = "blog_article"
    email = "email"
    social_longform = "social_longform"
    social_shortform = "social_shortform"
    video_script = "video_script"


class DeliveryDestination(str, Enum):
    hosted_by_us = "hosted_by_us"
    client_website = "client_website"
    linkedin = "linkedin"
    email_list = "email_list"
    tiktok = "tiktok"
    internal_only = "internal_only"


class DeliveryStrategy(str, Enum):
    single_canonical_article = "single_canonical_article"
    canonical_plus_short_social = "canonical_plus_short_social"


class PublicationCadence(str, Enum):
    on_demand = "on_demand"
    weekly = "weekly"
    twice_weekly = "twice_weekly"
    every_other_week = "every_other_week"
    daily = "daily"
    custom = "custom"


class Weekday(str, Enum):
    mon = "mon"
    tue = "tue"
    wed = "wed"
    thu = "thu"
    fri = "fri"
    sat = "sat"
    sun = "sun"


class Timezone(str, Enum):
    UTC = "UTC"
    Europe_London = "Europe_London"


class BrandSource(SchemaBase):
    source_id: str
    kind: BrandSourceKind
    purpose: BrandSourcePurpose
    ref: str
    notes: Optional[str] = None


class BrandSources(SchemaBase):
    require_at_least_one_of_purposes: List[BrandSourcePurpose]
    sources: List[BrandSource]

    @model_validator(mode="after")
    def _validate_requirements(self) -> "BrandSources":
        if not self.sources:
            raise ValueError("brand_sources.sources must not be empty")

        purposes_present = {s.purpose for s in self.sources}
        required_any_of = set(self.require_at_least_one_of_purposes)
        if required_any_of and purposes_present.isdisjoint(required_any_of):
            required = sorted(p.value for p in required_any_of)
            present = sorted(p.value for p in purposes_present)
            raise ValueError(
                "brand_sources must include at least one source with purpose in "
                f"{required}; present={present}"
            )

        return self


class Audience(SchemaBase):
    primary_audience: PrimaryAudience
    audience_sophistication: AudienceSophistication
    audience_context: Optional[str] = None


class ContentStrategy(SchemaBase):
    allowed_intents: List[ContentIntent]
    allowed_product_recommendation_forms: List[ProductRecommendationForm] = Field(default_factory=list)
    allowed_thought_leadership_forms: List[ThoughtLeadershipForm] = Field(default_factory=list)
    default_content_depth: ContentDepth


class TopicPolicy(SchemaBase):
    allowlist: List[str]

    @model_validator(mode="after")
    def _validate_allowlist(self) -> "TopicPolicy":
        cleaned: list[str] = []
        for t in self.allowlist:
            t2 = (t or "").strip()
            if not t2:
                raise ValueError("topic_policy.allowlist must not contain empty strings")
            cleaned.append(t2)

        if len(set(cleaned)) != len(cleaned):
            raise ValueError("topic_policy.allowlist must not contain duplicates")
        self.allowlist = cleaned
        return self


class PersonaConfig(SchemaBase):
    primary_persona: Persona
    persona_modifiers: List[PersonaModifier] = Field(default_factory=list)
    science_explicitness: ScienceExplicitness
    personal_presence: PersonalPresence
    narration_mode: NarrationMode


class CommercialPolicy(SchemaBase):
    commercial_posture: CommercialPosture
    cta_policy: CTAPolicy
    prohibited_behaviors: List[ProhibitedBehavior] = Field(default_factory=list)


class DisclaimerPolicy(SchemaBase):
    required: bool
    disclaimer_text: Optional[str] = None
    locations: List[DisclaimerLocation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_required(self) -> "DisclaimerPolicy":
        if self.required:
            if not self.disclaimer_text or not self.disclaimer_text.strip():
                raise ValueError("disclaimer_policy.disclaimer_text is required when required=true")
            if not self.locations:
                raise ValueError("disclaimer_policy.locations must not be empty when required=true")
        return self


class DeliveryPolicy(SchemaBase):
    delivery_channels: List[DeliveryChannel]
    delivery_destinations: List[DeliveryDestination]
    delivery_strategy: DeliveryStrategy
    auto_publish: bool


class Cadence(SchemaBase):
    publication_cadence: PublicationCadence
    preferred_publish_days: List[Weekday] = Field(default_factory=list)
    time_zone: Timezone

    @model_validator(mode="after")
    def _validate_custom(self) -> "Cadence":
        if self.publication_cadence == PublicationCadence.custom and not self.preferred_publish_days:
            raise ValueError("cadence.preferred_publish_days is required when publication_cadence=custom")
        return self


class BrandProfile(SchemaBase):
    brand_id: str
    brand_archetype: BrandArchetype

    brand_sources: BrandSources

    domains_supported: List[Domain]
    domain_primary: Domain

    audience: Audience

    content_strategy: ContentStrategy
    topic_policy: TopicPolicy

    persona_by_domain: Dict[Domain, PersonaConfig]

    commercial_policy: CommercialPolicy
    disclaimer_policy: DisclaimerPolicy
    delivery_policy: DeliveryPolicy
    cadence: Cadence

    @model_validator(mode="after")
    def _validate_domains(self) -> "BrandProfile":
        if self.domain_primary not in self.domains_supported:
            raise ValueError("domain_primary must be included in domains_supported")

        missing = [d for d in self.domains_supported if d not in self.persona_by_domain]
        if missing:
            missing_str = ", ".join(d.value for d in missing)
            raise ValueError(f"persona_by_domain must include configs for all domains_supported; missing={missing_str}")

        return self


class Publish(SchemaBase):
    publish_date: date


class Topic(SchemaBase):
    mode: TopicMode
    value: Optional[str] = None

    @model_validator(mode="after")
    def _validate_manual(self) -> "Topic":
        if self.mode == TopicMode.manual:
            if not self.value or not self.value.strip():
                raise ValueError("topic.value is required when topic.mode=manual")
            self.value = self.value.strip()
        elif self.value is not None:
            self.value = self.value.strip()
        return self


class DeliveryTarget(SchemaBase):
    destination: DeliveryDestination
    channel: DeliveryChannel


class ProductItem(SchemaBase):
    pick_id: str
    title: str
    url: str
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    provider: Optional[str] = None

    @model_validator(mode="after")
    def _validate_url(self) -> "ProductItem":
        if not self.url or not self.url.strip():
            raise ValueError("products.items.url must not be empty")
        self.url = self.url.strip()
        return self


class ProductsMode(str, Enum):
    none = "none"
    manual_list = "manual_list"


class Products(SchemaBase):
    mode: ProductsMode
    items: List[ProductItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_items(self) -> "Products":
        if self.mode == ProductsMode.none:
            if self.items:
                raise ValueError("products.items must be empty when products.mode=none")
        else:
            if not self.items:
                raise ValueError("products.items must not be empty when products.mode=manual_list")
        return self


Form = Union[ProductRecommendationForm, ThoughtLeadershipForm]


class ContentRequest(SchemaBase):
    brand_id: str
    publish: Publish

    intent: ContentIntent
    form: Form
    domain: Domain

    topic: Topic
    delivery_target: DeliveryTarget
    products: Products

    def is_product_form(self) -> bool:
        return isinstance(self.form, ProductRecommendationForm)
