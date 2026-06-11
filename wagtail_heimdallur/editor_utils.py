"""Editor-side text manipulation helpers mirrored by the TypeScript client."""

from wagtail_heimdallur.models import DiffAnnotation


def apply_annotation_correction(text: str, annotation: DiffAnnotation) -> str:
    """Apply a proofreading annotation to the original text."""
    return (
        text[:annotation.orig_start_idx]
        + annotation.changed_string
        + text[annotation.orig_end_idx:]
    )
