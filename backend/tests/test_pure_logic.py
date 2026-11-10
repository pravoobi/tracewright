"""Unit tests for pure (no DB / no LLM) logic that has already caused real bugs."""
import pytest

from backend.src.agents.healer import classify_failure_heuristic
from backend.src.ingestion.confidence import compute_chunk_confidence
from backend.src.ingestion.identity import match_to_existing, mint_logical_id
from backend.src.llm.client import extract_json_object
from backend.src.versioning.filtering import is_applicable


# --- extract_json_object -----------------------------------------------------
def test_json_plain():
    assert extract_json_object('{"a": 1}') == {"a": 1}


def test_json_fenced():
    assert extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}


def test_json_fence_with_trailing_prose():
    raw = '```json\n{"a": 1}\n```\nHope this helps!'
    assert extract_json_object(raw) == {"a": 1}


def test_json_bare_text_after_object():
    assert extract_json_object('{"a": 1} trailing') == {"a": 1}


def test_json_invalid_raises():
    with pytest.raises(ValueError):
        extract_json_object("not json")


# --- compute_chunk_confidence ------------------------------------------------
def test_confidence_passthrough():
    assert compute_chunk_confidence(0.95) == 0.95


def test_confidence_unresolved_xref_penalty():
    assert compute_chunk_confidence(0.95, has_unresolved_xrefs=True) == 0.855


def test_confidence_multiplies_signals():
    assert compute_chunk_confidence(0.9, ocr_confidence=0.5, table_confidence=0.5) == 0.225


def test_confidence_clamped():
    assert compute_chunk_confidence(2.0) == 1.0
    assert compute_chunk_confidence(-1.0) == 0.0


# --- identity ----------------------------------------------------------------
def test_logical_id_stable_across_renumbering_and_whitespace():
    a = mint_logical_id("3.4.2 The cart  shall hold 10 items.")
    b = mint_logical_id("5.1 the cart shall hold 10 items.")
    assert a == b
    assert a.startswith("REQ-")


def test_logical_id_differs_for_different_content():
    assert mint_logical_id("Cart holds 10 items") != mint_logical_id("Cart holds 20 items")


EXISTING = [
    {"logical_id": "REQ-a", "content": "A valid discount code reduces the order total by its percentage."},
    {"logical_id": "REQ-b", "content": "Orders below $10.00 cannot be placed."},
]


def test_match_survives_rewording():
    new = "A valid discount code reduces the order total by its stated percentage."
    assert match_to_existing(new, EXISTING) == "REQ-a"


def test_match_none_for_unrelated():
    assert match_to_existing("Passwords must contain a special character.", EXISTING) is None


def test_match_empty_existing():
    assert match_to_existing("anything", []) is None


# --- version filtering -------------------------------------------------------
ORDER = ["2.2", "2.3", "2.3.1", "2.4"]


def card(**kw):
    base = {"introduced_in_version": "2.3", "deprecated_in_version": None, "applicability": {}}
    base.update(kw)
    return base


def test_filter_introduced_after_env_excluded():
    assert not is_applicable(card(introduced_in_version="2.4"), "2.3", "staging", ORDER)


def test_filter_introduced_at_or_before_included():
    assert is_applicable(card(), "2.3", "staging", ORDER)
    assert is_applicable(card(), "2.4", "staging", ORDER)


def test_filter_deprecated_at_env_version_excluded():
    assert not is_applicable(card(deprecated_in_version="2.3.1"), "2.3.1", "staging", ORDER)
    assert is_applicable(card(deprecated_in_version="2.4"), "2.3.1", "staging", ORDER)


def test_filter_uses_declared_order_not_string_order():
    # "release-2.2-lts" sorts after "2.4" as a string, but is declared earliest here.
    order = ["release-2.2-lts", "2.3", "2.4"]
    assert is_applicable(card(introduced_in_version="release-2.2-lts"), "2.4", "staging", order)


def test_filter_allow_and_deny_lists():
    assert not is_applicable(card(applicability={"env_denylist": ["acme"]}), "2.4", "acme", ORDER)
    assert not is_applicable(card(applicability={"env_allowlist": ["prod"]}), "2.4", "staging", ORDER)
    assert is_applicable(card(applicability={"env_allowlist": ["staging"]}), "2.4", "staging", ORDER)


# --- healer failure classification -------------------------------------------
def test_not_found_is_locator_timing():
    msg = "Error: expect(locator).toHaveText failed\nwaiting for locator\nelement(s) not found"
    assert classify_failure_heuristic(msg) == "locator_timing"


def test_resolved_wrong_value_is_logic_even_with_waiting_text():
    # Same shape as a locator timeout, but "Received string" proves the locator resolved.
    msg = "expect(locator).toHaveText failed\nwaiting for locator('#total')\nReceived string: \"$40.00\""
    assert classify_failure_heuristic(msg) == "logic_assertion"


def test_generic_wait_is_locator_timing():
    assert classify_failure_heuristic("Timeout 5000ms exceeded. waiting for locator('#x')") == "locator_timing"


def test_unrecognised_error_is_ambiguous():
    assert classify_failure_heuristic("something unexpected") is None


# --- planner setup-manifest provenance ---------------------------------------
from backend.src.agents.planner import _mark_manifest_provenance  # noqa: E402

SRC = "A 20% discount code (SAVE20) applies to carts over $10.00. Quantity limit is 10."


def _card(manifest):
    return {"setup_manifest": manifest, "tier_sources": {"tier": 1, "confidence": 0.9}}


def test_manifest_grounded_entry_stays_document():
    c = _card([{"type": "discount_code", "code": "SAVE20", "percentage": 20, "source": "document"}])
    _mark_manifest_provenance(c, SRC)
    assert c["setup_manifest"][0]["source"] == "document"
    assert c["tier_sources"]["assumed_setup"] == 0


def test_manifest_invented_value_downgraded_even_if_model_claims_document():
    c = _card([{"type": "discount_code", "code": "SAVE15", "source": "document"}])
    _mark_manifest_provenance(c, SRC)
    assert c["setup_manifest"][0]["source"] == "assumed"
    assert c["tier_sources"]["assumed_setup"] == 1


def test_manifest_missing_source_defaults_to_assumed_and_structural_keys_ignored():
    c = _card([{"type": "user", "role": "authenticated_customer"}])
    _mark_manifest_provenance(c, SRC)
    assert c["setup_manifest"][0]["source"] == "assumed"


def test_manifest_empty_and_missing_tier_sources():
    c = {"setup_manifest": []}
    _mark_manifest_provenance(c, SRC)
    assert c["tier_sources"]["assumed_setup"] == 0
