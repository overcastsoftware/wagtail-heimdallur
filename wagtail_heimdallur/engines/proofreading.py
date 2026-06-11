"""Proofreading engine."""

import logging

from wagtail_heimdallur.backends import BackendRegistry
from wagtail_heimdallur.conf import get_settings
from wagtail_heimdallur.exceptions import BackendError
from wagtail_heimdallur.models import ProofreadingResult

logger = logging.getLogger(__name__)


class ProofreadingEngine:
    """Route proofreading requests to the configured backend registry."""

    def __init__(self, settings: dict | None = None, registry: BackendRegistry | None = None):
        self.registry = registry or BackendRegistry(settings or get_settings())

    def proofread(self, text: str, language: str) -> ProofreadingResult:
        """Proofread text using the backend selected for language."""
        try:
            logger.debug("Resolving proofreading backend for language '%s'", language)
            backend = self.registry.get_backend_for_proofreading(language)
            logger.debug(
                "Invoking proofreading backend %s for language '%s'",
                backend.__class__.__name__,
                language,
            )
            return backend.proofread(text, language)
        except BackendError:
            raise
        except Exception as exc:
            logger.exception("Unexpected proofreading backend failure.")
            raise BackendError("Unexpected proofreading backend failure.") from exc
