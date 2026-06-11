"""Hypothesis strategies for generating wagtail_heimdallur data models."""

from hypothesis import strategies as st

from wagtail_heimdallur.models import DiffAnnotation, ProofreadingResult


# Known change types that the proofreading system can produce
CHANGE_TYPES = ["spelling", "grammar", "style", "punctuation", "capitalization"]


@st.composite
def diff_annotation_strategy(draw):
    """Generate a valid DiffAnnotation with consistent index constraints.

    Ensures orig_start_idx <= orig_end_idx and changed_start_idx <= changed_end_idx.
    """
    orig_start_idx = draw(st.integers(min_value=0, max_value=1000))
    orig_end_idx = draw(st.integers(min_value=orig_start_idx, max_value=orig_start_idx + 200))
    orig_string = draw(st.text(min_size=0, max_size=50))

    changed_start_idx = draw(st.integers(min_value=0, max_value=1000))
    changed_end_idx = draw(st.integers(min_value=changed_start_idx, max_value=changed_start_idx + 200))
    changed_string = draw(st.text(min_size=0, max_size=50))

    change_type = draw(st.sampled_from(CHANGE_TYPES))

    return DiffAnnotation(
        orig_start_idx=orig_start_idx,
        orig_end_idx=orig_end_idx,
        orig_string=orig_string,
        changed_start_idx=changed_start_idx,
        changed_end_idx=changed_end_idx,
        changed_string=changed_string,
        change_type=change_type,
    )


@st.composite
def proofreading_result_strategy(draw):
    """Generate a valid ProofreadingResult with arbitrary text and annotations."""
    original_text = draw(st.text(min_size=0, max_size=500))
    corrected_text = draw(st.text(min_size=0, max_size=500))
    annotations = draw(st.lists(diff_annotation_strategy(), min_size=0, max_size=10))

    return ProofreadingResult(
        original_text=original_text,
        corrected_text=corrected_text,
        annotations=annotations,
    )
