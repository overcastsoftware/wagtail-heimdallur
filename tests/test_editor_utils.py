"""Property tests for editor correction helpers."""

from hypothesis import given, settings
from hypothesis import strategies as st

from wagtail_heimdallur.editor_utils import apply_annotation_correction
from wagtail_heimdallur.models import DiffAnnotation


@given(
    prefix=st.text(max_size=50),
    original=st.text(min_size=1, max_size=50),
    suffix=st.text(max_size=50),
    replacement=st.text(max_size=50),
)
@settings(max_examples=100)
def test_annotation_correction_application(prefix, original, suffix, replacement):
    """Property 14: applying a DiffAnnotation replaces exactly its substring."""
    text = f"{prefix}{original}{suffix}"
    annotation = DiffAnnotation(
        orig_start_idx=len(prefix),
        orig_end_idx=len(prefix) + len(original),
        orig_string=original,
        changed_start_idx=len(prefix),
        changed_end_idx=len(prefix) + len(replacement),
        changed_string=replacement,
        change_type="replacement",
    )

    assert apply_annotation_correction(text, annotation) == f"{prefix}{replacement}{suffix}"
