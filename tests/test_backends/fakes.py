"""Fake backend classes used by registry tests."""

from wagtail_heimdallur.backends.base import (
    BaseProofreadingBackend,
    BaseTranslationBackend,
)
from wagtail_heimdallur.models import ProofreadingResult


class FakeCombinedBackend(BaseProofreadingBackend, BaseTranslationBackend):
    """Configurable backend supporting both operation types."""

    def __init__(
        self,
        label="backend",
        proofreading_languages=None,
        translation_pairs=None,
        **kwargs,
    ):
        self.label = label
        self.options = kwargs
        self.proofreading_languages = list(proofreading_languages or [])
        self.translation_pairs = [
            tuple(pair) for pair in (translation_pairs or [])
        ]

    def proofread(self, text: str, language: str) -> ProofreadingResult:
        return ProofreadingResult(
            original_text=text,
            corrected_text=text,
            annotations=[],
        )

    def get_supported_languages(self) -> list[str]:
        return self.proofreading_languages

    def translate(self, text: str, source_language: str, target_language: str) -> str:
        return text

    def get_supported_language_pairs(self) -> list[tuple[str, str]]:
        return self.translation_pairs


class FakeProofreadingBackend(BaseProofreadingBackend):
    """Configurable proofreading-only backend."""

    def __init__(self, label="backend", proofreading_languages=None, **kwargs):
        self.label = label
        self.options = kwargs
        self.proofreading_languages = list(proofreading_languages or [])

    def proofread(self, text: str, language: str) -> ProofreadingResult:
        return ProofreadingResult(
            original_text=text,
            corrected_text=text,
            annotations=[],
        )

    def get_supported_languages(self) -> list[str]:
        return self.proofreading_languages


class FakeTranslationBackend(BaseTranslationBackend):
    """Configurable translation-only backend."""

    def __init__(self, label="backend", translation_pairs=None, **kwargs):
        self.label = label
        self.options = kwargs
        self.translation_pairs = [
            tuple(pair) for pair in (translation_pairs or [])
        ]

    def translate(self, text: str, source_language: str, target_language: str) -> str:
        return text

    def get_supported_language_pairs(self) -> list[tuple[str, str]]:
        return self.translation_pairs


class OptionCaptureBackend(FakeCombinedBackend):
    """Backend that records constructor kwargs for pass-through assertions."""

    last_options = None

    def __init__(self, **kwargs):
        type(self).last_options = kwargs.copy()
        super().__init__(**kwargs)
