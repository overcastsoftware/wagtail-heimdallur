"""Tests for Heimdallur management commands."""

from io import StringIO

from django.core.management import call_command
from django.test import override_settings
from hypothesis import assume, given, settings
from hypothesis import strategies as st


language_codes = st.text(
    alphabet=st.characters(min_codepoint=97, max_codepoint=122),
    min_size=2,
    max_size=5,
)
backend_ids = st.text(
    alphabet=st.characters(min_codepoint=97, max_codepoint=122),
    min_size=1,
    max_size=10,
)


@given(
    backend_id=backend_ids,
    proofreading_language=language_codes,
    source_language=language_codes,
    target_language=language_codes,
    inline_proofreading=st.booleans(),
    inline_translation=st.booleans(),
    page_translation=st.booleans(),
)
@settings(max_examples=50)
def test_heimdallur_check_output_completeness(
    backend_id,
    proofreading_language,
    source_language,
    target_language,
    inline_proofreading,
    inline_translation,
    page_translation,
):
    """Property 19: command output contains features, backends, and routes."""
    assume(source_language != target_language)
    config = {
        "FEATURES": {
            "inline_proofreading": inline_proofreading,
            "inline_translation": inline_translation,
            "page_translation": page_translation,
        },
        "BACKENDS": {
            backend_id: {
                "CLASS": "tests.test_backends.fakes.FakeCombinedBackend",
                "OPTIONS": {
                    "proofreading_languages": [proofreading_language],
                    "translation_pairs": [(source_language, target_language)],
                },
                "enabled": True,
            }
        },
        "LANGUAGE_ROUTING": {
            "proofreading": {
                proofreading_language: backend_id,
            },
            "translation": {
                (source_language, target_language): backend_id,
            },
        },
    }
    output = StringIO()

    with override_settings(WAGTAIL_HEIMDALLUR=config):
        call_command("heimdallur_check", stdout=output)

    rendered = output.getvalue()
    for feature_name in config["FEATURES"]:
        assert feature_name in rendered
    assert backend_id in rendered
    assert proofreading_language in rendered
    assert f"{source_language}->{target_language}" in rendered
