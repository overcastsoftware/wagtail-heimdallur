"""Property-based tests for ProofreadingResult serialization round-trip."""

from hypothesis import given, settings

from wagtail_heimdallur.models import ProofreadingResult
from tests.strategies import proofreading_result_strategy


# Feature: wagtail-heimdallur, Property 1: ProofreadingResult serialization round-trip
# **Validates: Requirements 11.1, 11.2, 11.3**
@given(result=proofreading_result_strategy())
@settings(max_examples=100)
def test_proofreading_result_round_trip(result: ProofreadingResult):
    """For any valid ProofreadingResult, serializing to JSON then deserializing
    back SHALL produce an equivalent ProofreadingResult object."""
    json_str = result.to_json()
    deserialized = ProofreadingResult.from_json(json_str)

    assert deserialized.original_text == result.original_text
    assert deserialized.corrected_text == result.corrected_text
    assert len(deserialized.annotations) == len(result.annotations)

    for orig_ann, deser_ann in zip(result.annotations, deserialized.annotations):
        assert deser_ann.orig_start_idx == orig_ann.orig_start_idx
        assert deser_ann.orig_end_idx == orig_ann.orig_end_idx
        assert deser_ann.orig_string == orig_ann.orig_string
        assert deser_ann.changed_start_idx == orig_ann.changed_start_idx
        assert deser_ann.changed_end_idx == orig_ann.changed_end_idx
        assert deser_ann.changed_string == orig_ann.changed_string
        assert deser_ann.change_type == orig_ann.change_type

    # Also verify full object equality via dataclass __eq__
    assert deserialized == result
