"""Abstract base classes for Wagtail-Heimdallur backends."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Tuple

from wagtail_heimdallur.models import ProofreadingResult


@dataclass
class TextTranslationStatus:
    """Status returned by an asynchronous text translation task."""

    task_id: str
    status: str
    progress: float = 0
    text: str | None = None
    error: str | None = None
    message: str | None = None


class BaseProofreadingBackend(ABC):
    """Abstract base class for proofreading backends."""

    def __init__(self, **kwargs):
        """Initialize with backend-specific configuration options."""

    @abstractmethod
    def proofread(self, text: str, language: str) -> ProofreadingResult:
        """Proofread text and return annotated corrections."""

    @abstractmethod
    def get_supported_languages(self) -> List[str]:
        """Return language codes supported for proofreading."""


class BaseTranslationBackend(ABC):
    """Abstract base class for translation backends."""

    def __init__(self, **kwargs):
        """Initialize with backend-specific configuration options."""

    @abstractmethod
    def translate(self, text: str, source_language: str, target_language: str) -> str:
        """Translate text from source_language to target_language."""

    @abstractmethod
    def get_supported_language_pairs(self) -> List[Tuple[str, str]]:
        """Return supported translation language pairs."""
