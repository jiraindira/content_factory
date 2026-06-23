"""
Client Onboarding UI
Run with: streamlit run onboarding_ui.py
"""

import os
from pathlib import Path

import streamlit as st
import yaml

BRANDS_DIR = Path(__file__).parent / "content_factory" / "brands"

# ── Enum options (mirrors models.py) ────────────────────────────────────────
ARCHETYPES = ["mentor_coach", "product_ranker", "product_guide", "reviewer", "travel_guide"]

ARCHETYPE_TIPS = {
    "mentor_coach": "Shares frameworks, lessons, and personal growth advice. Speaks like a trusted teacher or consultant.",
    "product_ranker": "Publishes best-of lists, top 10s, and category comparisons. Authority comes from breadth of research.",
    "product_guide": "Deep expert on one specific product or niche. Readers come for the definitive word on that thing.",
    "reviewer": "Opinionated evaluations of specific things — restaurants, gear, hotels, cities. Voice is personal and direct.",
    "travel_guide": "Destination and experience-led storytelling. Paints a picture of places and inspires the reader to go.",
}
DOMAINS = ["leadership", "finance", "health", "pets", "home", "kitchen", "tech"]
AUDIENCES = [
    "senior_executives_c_suite", "mid_level_leaders", "founders_entrepreneurs",
    "sales_leaders", "professional_speakers", "coaches_consultants",
    "general_consumers", "enthusiasts_hobbyists",
]
SOPHISTICATION = ["low", "medium", "high"]
INTENTS = ["product_recommendation", "product_education", "thought_leadership", "opinion_pov", "digest_curation"]
PRODUCT_FORMS = ["top_x_list", "in_depth_single_review", "comparison_table", "buyer_guide", "alternatives_roundup"]
TL_FORMS = [
    "core_insight_essay", "framework_breakdown", "contrarian_take",
    "myths_vs_reality", "narrative_with_lesson", "micro_case_study", "question_led_exploration",
]
DEPTH = ["micro", "short", "medium", "long"]
PERSONAS = [
    "practical_expert", "warm_reflective", "quirky_fun", "minimalist_direct",
    "deeply_technical", "calm_authoritative", "direct_insight_dense",
    "provocative_challenger", "minimalist_executive",
]
PERSONA_MODIFIERS = ["none", "science_led_explainer", "reassuring", "slightly_playful"]
SCIENCE_EXP = ["implied", "explicit_when_credibility_helpful", "explicit_often"]
PERSONAL_PRESENCE = ["none", "occasional_personal_anecdotes", "frequent_personal_anecdotes"]
NARRATION = ["third_person_only", "first_person_allowed", "first_person_preferred"]
COMMERCIAL_POSTURE = ["invisible", "soft_recommendation", "clear_recommendation", "explicit_cta"]
CTA_POLICY = ["none", "soft_authority_signature_line", "gentle_cta_at_end", "clear_invitation"]
PROHIBITED = ["fake_scarcity", "hype_superlatives", "pressure_language"]
CHANNELS = ["blog_article", "email", "social_longform", "social_shortform", "video_script"]
DESTINATIONS = ["hosted_by_us", "client_website", "linkedin", "email_list", "instagram", "tiktok", "internal_only"]
STRATEGIES = ["single_canonical_article", "canonical_plus_short_social"]
CADENCE = ["on_demand", "weekly", "twice_weekly", "every_other_week", "daily", "custom"]
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DISCLAIMER_LOCS = ["header", "footer", "before_products"]
SOURCE_PURPOSES = ["homepage", "linkedin_profile", "about_page", "services_page", "product_pages", "policies", "longform_content", "other"]


# ── Helpers ──────────────────────────────────────────────────────────────────
def list_brands() -> list[str]:
    if not BRANDS_DIR.exists():
        return []
    return sorted(p.stem for p in BRANDS_DIR.glob("*.yaml"))


def load_brand(brand_id: str) -> dict:
    path = BRANDS_DIR / f"{brand_id}.yaml"
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


def save_brand(data: dict) -> Path:
    BRANDS_DIR.mkdir(parents=True, exist_ok=True)
    path = BRANDS_DIR / f"{data['brand_id']}.yaml"
    with open(path, "w") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)
    return path


def pick(d: dict, *keys, default=None):
    """Safe nested get."""
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default if k == keys[-1] else {})
    return d


def idx(options: list, value, default=0) -> int:
    try:
        return options.index(value)
    except (ValueError, TypeError):
        return default


def multi_idx(options: list, values) -> list:
    if not values:
        return []
    return [o for o in options if o in values]


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Content Factory — Client Onboarding", layout="wide")
st.title("Content Factory — Client Onboarding")

# ── Sidebar: client selector ──────────────────────────────────────────────────
st.sidebar.header("Client")
brands = list_brands()
NEW = "➕ New client"
options = [NEW] + brands
choice = st.sidebar.selectbox("Select client", options)

if "loaded_brand" not in st.session_state:
    st.session_state.loaded_brand = {}

brand_switched = st.session_state.get("_last_choice") != choice

if choice == NEW:
    if brand_switched:
        st.session_state.loaded_brand = {}
        st.session_state._last_choice = choice
        # clear source session state keys so form starts fresh
        for k in list(st.session_state.keys()):
            if k.startswith("src_"):
                del st.session_state[k]
    raw = st.session_state.loaded_brand
else:
    if brand_switched:
        st.session_state.loaded_brand = load_brand(choice)
        st.session_state._last_choice = choice
        # seed source fields into session state so value= doesn't clobber them on rerun
        sources_data = pick(st.session_state.loaded_brand, "brand_sources", "sources") or []
        for k in list(st.session_state.keys()):
            if k.startswith("src_"):
                del st.session_state[k]
        for i, s in enumerate(sources_data):
            st.session_state[f"src_id_{i}"] = s.get("source_id", f"source_{i+1}")
            st.session_state[f"src_purpose_{i}"] = s.get("purpose", "homepage")
            st.session_state[f"src_kind_{i}"] = s.get("kind", "url")
            st.session_state[f"src_ref_{i}"] = s.get("ref", "")
    raw = st.session_state.loaded_brand

# ── Identity (outside form so creator role tooltip updates live) ──────────────
st.subheader("Identity")
c1, c2 = st.columns(2)
with c1:
    brand_id = st.text_input("Brand ID (slug, no spaces)", value=raw.get("brand_id", ""))
with c2:
    current_archetype = raw.get("brand_archetype", ARCHETYPES[0])
    brand_archetype = st.selectbox(
        "Creator role",
        ARCHETYPES,
        index=idx(ARCHETYPES, current_archetype),
        format_func=lambda x: x.replace("_", " ").title(),
    )
    st.caption(f"ℹ️ {ARCHETYPE_TIPS.get(brand_archetype, '')}")

with st.form("onboarding"):

    # ── Brand sources ─────────────────────────────────────────────────────────
    st.subheader("Brand sources")
    st.caption("Add the URLs or files we should use to understand this brand's voice.")
    num_sources = st.number_input("Number of sources", min_value=1, max_value=8, value=max(1, len(pick(raw, "brand_sources", "sources") or [])))
    sources_out = []
    for i in range(int(num_sources)):
        # seed defaults for new rows that don't yet have a session state entry
        if f"src_id_{i}" not in st.session_state:
            st.session_state[f"src_id_{i}"] = f"source_{i+1}"
        if f"src_ref_{i}" not in st.session_state:
            st.session_state[f"src_ref_{i}"] = ""
        sc1, sc2, sc3, sc4 = st.columns([1, 1, 2, 3])
        with sc1:
            sid = st.text_input(f"ID #{i+1}", key=f"src_id_{i}")
        with sc2:
            spurpose = st.selectbox(f"Purpose #{i+1}", SOURCE_PURPOSES, key=f"src_purpose_{i}")
        with sc3:
            skind = st.selectbox(f"Kind #{i+1}", ["url", "file"], key=f"src_kind_{i}")
        with sc4:
            sref = st.text_input(f"URL / path #{i+1}", key=f"src_ref_{i}")
        sources_out.append({"source_id": sid, "kind": skind, "purpose": spurpose, "ref": sref})

    # ── Domains ───────────────────────────────────────────────────────────────
    st.subheader("Domains")
    c1, c2 = st.columns(2)
    with c1:
        domains_supported = st.multiselect(
            "Domains supported",
            DOMAINS,
            default=multi_idx(DOMAINS, raw.get("domains_supported", [])),
        )
    with c2:
        domain_primary = st.selectbox(
            "Primary domain",
            domains_supported if domains_supported else DOMAINS,
            index=idx(domains_supported if domains_supported else DOMAINS, raw.get("domain_primary")),
        )

    # ── Audience ──────────────────────────────────────────────────────────────
    st.subheader("Audience")
    c1, c2, c3 = st.columns(3)
    with c1:
        primary_audience = st.selectbox("Primary audience", AUDIENCES, index=idx(AUDIENCES, pick(raw, "audience", "primary_audience")))
    with c2:
        audience_sophistication = st.selectbox("Sophistication", SOPHISTICATION, index=idx(SOPHISTICATION, pick(raw, "audience", "audience_sophistication", default="medium")))
    with c3:
        audience_context = st.text_input("Audience context (optional)", value=pick(raw, "audience", "audience_context") or "")

    # ── Content strategy ──────────────────────────────────────────────────────
    st.subheader("Content strategy")
    allowed_intents = st.multiselect("Allowed intents", INTENTS, default=multi_idx(INTENTS, pick(raw, "content_strategy", "allowed_intents") or []))
    c1, c2, c3 = st.columns(3)
    with c1:
        allowed_pr_forms = st.multiselect("Product recommendation forms", PRODUCT_FORMS, default=multi_idx(PRODUCT_FORMS, pick(raw, "content_strategy", "allowed_product_recommendation_forms") or []))
    with c2:
        allowed_tl_forms = st.multiselect("Thought leadership forms", TL_FORMS, default=multi_idx(TL_FORMS, pick(raw, "content_strategy", "allowed_thought_leadership_forms") or []))
    with c3:
        default_depth = st.selectbox("Default content depth", DEPTH, index=idx(DEPTH, pick(raw, "content_strategy", "default_content_depth", default="medium")))

    # ── Topic policy ──────────────────────────────────────────────────────────
    st.subheader("Topic allowlist")
    topic_raw = "\n".join(pick(raw, "topic_policy", "allowlist") or [])
    topic_text = st.text_area("One topic per line", value=topic_raw, height=120)

    # ── Persona by domain ─────────────────────────────────────────────────────
    st.subheader("Persona by domain")
    st.caption("Configure the writing persona for each supported domain.")
    persona_by_domain_out = {}
    for domain in (domains_supported or []):
        existing_p = pick(raw, "persona_by_domain", domain) or {}
        with st.expander(f"Persona — {domain}", expanded=False):
            pc1, pc2, pc3, pc4, pc5 = st.columns(5)
            with pc1:
                pp = st.selectbox("Primary persona", PERSONAS, index=idx(PERSONAS, existing_p.get("primary_persona")), key=f"pp_{domain}")
            with pc2:
                pm = st.multiselect("Modifiers", PERSONA_MODIFIERS, default=multi_idx(PERSONA_MODIFIERS, existing_p.get("persona_modifiers", ["none"])), key=f"pm_{domain}")
            with pc3:
                se = st.selectbox("Science explicitness", SCIENCE_EXP, index=idx(SCIENCE_EXP, existing_p.get("science_explicitness", "implied")), key=f"se_{domain}")
            with pc4:
                presence = st.selectbox("Personal presence", PERSONAL_PRESENCE, index=idx(PERSONAL_PRESENCE, existing_p.get("personal_presence", "none")), key=f"pres_{domain}")
            with pc5:
                narration = st.selectbox("Narration mode", NARRATION, index=idx(NARRATION, existing_p.get("narration_mode", "third_person_only")), key=f"narr_{domain}")
        persona_by_domain_out[domain] = {
            "primary_persona": pp,
            "persona_modifiers": pm if pm else ["none"],
            "science_explicitness": se,
            "personal_presence": presence,
            "narration_mode": narration,
        }

    # ── Commercial policy ─────────────────────────────────────────────────────
    st.subheader("Commercial policy")
    c1, c2, c3 = st.columns(3)
    with c1:
        commercial_posture = st.selectbox("Posture", COMMERCIAL_POSTURE, index=idx(COMMERCIAL_POSTURE, pick(raw, "commercial_policy", "commercial_posture", default="invisible")))
    with c2:
        cta_policy = st.selectbox("CTA policy", CTA_POLICY, index=idx(CTA_POLICY, pick(raw, "commercial_policy", "cta_policy", default="none")))
    with c3:
        prohibited_behaviors = st.multiselect("Prohibited behaviors", PROHIBITED, default=multi_idx(PROHIBITED, pick(raw, "commercial_policy", "prohibited_behaviors") or []))

    # ── Disclaimer ────────────────────────────────────────────────────────────
    st.subheader("Disclaimer")
    c1, c2 = st.columns([1, 3])
    with c1:
        disclaimer_required = st.checkbox("Disclaimer required", value=pick(raw, "disclaimer_policy", "required") or False)
        disclaimer_locs = st.multiselect("Locations", DISCLAIMER_LOCS, default=multi_idx(DISCLAIMER_LOCS, pick(raw, "disclaimer_policy", "locations") or []))
    with c2:
        disclaimer_text = st.text_area("Disclaimer text", value=pick(raw, "disclaimer_policy", "disclaimer_text") or "", height=80)

    # ── Delivery policy ───────────────────────────────────────────────────────
    st.subheader("Delivery")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        delivery_channels = st.multiselect("Channels", CHANNELS, default=multi_idx(CHANNELS, pick(raw, "delivery_policy", "delivery_channels") or []))
    with c2:
        delivery_destinations = st.multiselect("Destinations", DESTINATIONS, default=multi_idx(DESTINATIONS, pick(raw, "delivery_policy", "delivery_destinations") or []))
    with c3:
        delivery_strategy = st.selectbox("Strategy", STRATEGIES, index=idx(STRATEGIES, pick(raw, "delivery_policy", "delivery_strategy", default="single_canonical_article")))
    with c4:
        auto_publish = st.checkbox("Auto publish", value=pick(raw, "delivery_policy", "auto_publish") or False)

    # ── Cadence ───────────────────────────────────────────────────────────────
    st.subheader("Cadence")
    c1, c2, c3 = st.columns(3)
    with c1:
        publication_cadence = st.selectbox("Publication cadence", CADENCE, index=idx(CADENCE, pick(raw, "cadence", "publication_cadence", default="on_demand")))
    with c2:
        preferred_days = st.multiselect("Preferred publish days", WEEKDAYS, default=multi_idx(WEEKDAYS, pick(raw, "cadence", "preferred_publish_days") or []))
    with c3:
        time_zone = st.selectbox("Time zone", ["UTC", "Europe_London"], index=idx(["UTC", "Europe_London"], pick(raw, "cadence", "time_zone", default="UTC")))

    # ── Submit ────────────────────────────────────────────────────────────────
    submitted = st.form_submit_button("💾 Save brand profile", use_container_width=True, type="primary")

# ── Save logic ────────────────────────────────────────────────────────────────
if submitted:
    errors = []
    if not brand_id.strip():
        errors.append("Brand ID is required.")
    if not domains_supported:
        errors.append("At least one domain must be selected.")
    if domain_primary not in domains_supported:
        errors.append("Primary domain must be one of the supported domains.")
    if not allowed_intents:
        errors.append("At least one intent must be selected.")

    if errors:
        for e in errors:
            st.error(e)
    else:
        topic_allowlist = [t.strip() for t in topic_text.splitlines() if t.strip()]

        data = {
            "brand_id": brand_id.strip(),
            "brand_archetype": brand_archetype,
            "brand_sources": {
                "require_at_least_one_of_purposes": ["homepage"],
                "sources": sources_out,
            },
            "domains_supported": domains_supported,
            "domain_primary": domain_primary,
            "audience": {
                "primary_audience": primary_audience,
                "audience_sophistication": audience_sophistication,
                "audience_context": audience_context or "",
            },
            "content_strategy": {
                "allowed_intents": allowed_intents,
                "allowed_product_recommendation_forms": allowed_pr_forms,
                "allowed_thought_leadership_forms": allowed_tl_forms,
                "default_content_depth": default_depth,
            },
            "topic_policy": {
                "allowlist": topic_allowlist,
            },
            "persona_by_domain": persona_by_domain_out,
            "commercial_policy": {
                "commercial_posture": commercial_posture,
                "cta_policy": cta_policy,
                "prohibited_behaviors": prohibited_behaviors,
            },
            "disclaimer_policy": {
                "required": disclaimer_required,
                "disclaimer_text": disclaimer_text or "",
                "locations": disclaimer_locs,
            },
            "delivery_policy": {
                "delivery_channels": delivery_channels,
                "delivery_destinations": delivery_destinations,
                "delivery_strategy": delivery_strategy,
                "auto_publish": auto_publish,
            },
            "cadence": {
                "publication_cadence": publication_cadence,
                "preferred_publish_days": preferred_days,
                "time_zone": time_zone,
            },
        }

        path = save_brand(data)
        st.success(f"Saved to `{path}`")
        st.session_state.loaded_brand = data
        st.session_state._last_choice = brand_id.strip()
        st.balloons()
