"""Translation engine."""

import logging

from wagtail_heimdallur.backends import BackendRegistry
from wagtail_heimdallur.conf import get_settings
from wagtail_heimdallur.exceptions import BackendError

logger = logging.getLogger(__name__)


class TranslationEngine:
    """Route translation requests to the configured backend registry."""

    def __init__(self, settings: dict | None = None, registry: BackendRegistry | None = None):
        self.registry = registry or BackendRegistry(settings or get_settings())

    def translate(self, text: str, source_language: str, target_language: str) -> str:
        """Translate text using the backend selected for the language pair."""
        try:
            logger.debug(
                "Resolving translation backend for language pair '%s' -> '%s'",
                source_language,
                target_language,
            )
            backend = self.registry.get_backend_for_translation(
                source_language,
                target_language,
            )
            logger.debug(
                "Invoking translation backend %s for language pair '%s' -> '%s'",
                backend.__class__.__name__,
                source_language,
                target_language,
            )
            return backend.translate(text, source_language, target_language)
        except BackendError:
            raise
        except Exception as exc:
            logger.exception("Unexpected translation backend failure.")
            raise BackendError("Unexpected translation backend failure.") from exc
