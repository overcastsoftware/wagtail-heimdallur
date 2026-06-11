"""Tests for TranslationEngine."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from wagtail_heimdallur.engines.translation import TranslationEngine
from wagtail_heimdallur.exceptions import BackendError, BackendRequestError


class StubRegistry:
    def __init__(self, backend):
        self.backend = backend

    def get_backend_for_translation(self, source_language, target_language):
        return self.backend


class ExplodingTranslationBackend:
    def translate(self, text, source_language, target_language):
        raise ValueError("unexpected")


class BackendErrorTranslationBackend:
    def translate(self, text, source_language, target_language):
        raise BackendRequestError("backend rejected request")


class EchoTranslationBackend:
    def translate(self, text, source_language, target_language):
        return f"{source_language}:{target_language}:{text}"


@given(
    text=st.text(max_size=200),
    source_language=st.text(min_size=1, max_size=8),
    target_language=st.text(min_size=1, max_size=8),
)
@settings(max_examples=50)
def test_unexpected_translation_exceptions_wrapped_as_backend_error(
    text,
    source_language,
    target_language,
):
    """Property 15: unexpected backend exceptions are wrapped as BackendError."""
    engine = TranslationEngine(registry=StubRegistry(ExplodingTranslationBackend()))

    with pytest.raises(BackendError) as exc_info:
        engine.translate(text, source_language, target_language)

    assert isinstance(exc_info.value.__cause__, ValueError)


def test_backend_errors_are_not_double_wrapped():
    engine = TranslationEngine(registry=StubRegistry(BackendErrorTranslationBackend()))

    with pytest.raises(BackendRequestError):
        engine.translate("text", "is", "en")


@given(
    text=st.text(max_size=200),
    source_language=st.text(min_size=1, max_size=8),
    target_language=st.text(min_size=1, max_size=8),
)
@settings(max_examples=50)
def test_no_partial_translation_modifications_on_backend_failure(
    text,
    source_language,
    target_language,
):
    """Property 16: failed translation leaves caller-owned input unchanged."""
    original_text = text
    original_source_language = source_language
    original_target_language = target_language
    engine = TranslationEngine(registry=StubRegistry(ExplodingTranslationBackend()))

    with pytest.raises(BackendError):
        engine.translate(text, source_language, target_language)

    assert text == original_text
    assert source_language == original_source_language
    assert target_language == original_target_language


def test_translation_engine_invokes_selected_backend():
    engine = TranslationEngine(registry=StubRegistry(EchoTranslationBackend()))

    assert engine.translate("halló", "is", "en") == "is:en:halló"
