"""Tests for ProofreadingEngine."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from wagtail_heimdallur.engines.proofreading import ProofreadingEngine
from wagtail_heimdallur.exceptions import BackendError, BackendRequestError
from wagtail_heimdallur.models import ProofreadingResult


class StubRegistry:
    def __init__(self, backend):
        self.backend = backend

    def get_backend_for_proofreading(self, language):
        return self.backend


class ExplodingProofreadingBackend:
    def proofread(self, text, language):
        raise ValueError("unexpected")


class BackendErrorProofreadingBackend:
    def proofread(self, text, language):
        raise BackendRequestError("backend rejected request")


class EchoProofreadingBackend:
    def proofread(self, text, language):
        return ProofreadingResult(
            original_text=text,
            corrected_text=text,
            annotations=[],
        )


@given(text=st.text(max_size=200), language=st.text(min_size=1, max_size=8))
@settings(max_examples=50)
def test_unexpected_proofreading_exceptions_wrapped_as_backend_error(text, language):
    """Property 15: unexpected backend exceptions are wrapped as BackendError."""
    engine = ProofreadingEngine(registry=StubRegistry(ExplodingProofreadingBackend()))

    with pytest.raises(BackendError) as exc_info:
        engine.proofread(text, language)

    assert isinstance(exc_info.value.__cause__, ValueError)


def test_backend_errors_are_not_double_wrapped():
    engine = ProofreadingEngine(registry=StubRegistry(BackendErrorProofreadingBackend()))

    with pytest.raises(BackendRequestError):
        engine.proofread("text", "is")


@given(text=st.text(max_size=200), language=st.text(min_size=1, max_size=8))
@settings(max_examples=50)
def test_no_partial_proofreading_modifications_on_backend_failure(text, language):
    """Property 16: failed proofreading leaves caller-owned input unchanged."""
    original_text = text
    original_language = language
    engine = ProofreadingEngine(registry=StubRegistry(ExplodingProofreadingBackend()))

    with pytest.raises(BackendError):
        engine.proofread(text, language)

    assert text == original_text
    assert language == original_language


def test_proofreading_engine_invokes_selected_backend():
    engine = ProofreadingEngine(registry=StubRegistry(EchoProofreadingBackend()))

    result = engine.proofread("halló", "is")

    assert result == ProofreadingResult(
        original_text="halló",
        corrected_text="halló",
        annotations=[],
    )
