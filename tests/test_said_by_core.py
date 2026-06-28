"""
Smoke tests for the live Said By core (Claude generation + book grounding).
Network-free — exercises the pure logic, not the LLM API.
"""
import importlib

from content_factory import references
from content_factory.article_writer import _ARTICLE_SCHEMA, _build_voice_block
from content_factory.topic_generator import _TOPICS_SCHEMA
from integrations import claude_adapters


def test_reference_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(references, "REFERENCES_DIR", tmp_path)
    assert references.reference_meta("acme") == {"exists": False}

    references.save_reference_text("acme", "Chapter one. " * 100)
    meta = references.reference_meta("acme")
    assert meta["exists"] and meta["word_count"] == 200
    assert references.load_reference_text("acme")

    assert references.delete_reference("acme") is True
    assert references.reference_meta("acme") == {"exists": False}


def test_reference_caps_large_text(tmp_path, monkeypatch):
    monkeypatch.setattr(references, "REFERENCES_DIR", tmp_path)
    references.save_reference_text("big", "x" * (references.MAX_CHARS + 50_000))
    assert references.reference_meta("big")["char_count"] == references.MAX_CHARS


def test_generation_schemas_are_wellformed():
    for schema in (_ARTICLE_SCHEMA, _TOPICS_SCHEMA):
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert schema["required"]
    assert set(_ARTICLE_SCHEMA["required"]) == {"title", "body"}
    assert _TOPICS_SCHEMA["required"] == ["topics"]


def test_claude_strip_fences():
    fenced = "```json\n{\"a\": 1}\n```"
    assert claude_adapters._strip_fences(fenced) == '{"a": 1}'
    assert claude_adapters._strip_fences('{"a": 1}') == '{"a": 1}'


def test_voice_block_reflects_persona():
    brand = {
        "brand_archetype": "mentor_coach",
        "domains_supported": ["leadership"],
        "audience": {"primary_audience": "c_suite_senior_leaders"},
        "persona_by_domain": {
            "leadership": {
                "primary_persona": "warm_reflective",
                "narration_mode": "first_person_preferred",
                "personal_presence": "occasional_personal_anecdotes",
            }
        },
    }
    block = _build_voice_block(brand)
    assert "warm" in block.lower()
    assert "first-person" in block.lower()


def test_default_model_is_claude():
    importlib.reload(claude_adapters)
    assert claude_adapters.DEFAULT_MODEL.startswith("claude-")
