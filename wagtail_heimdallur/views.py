"""API views for Wagtail-Heimdallur."""

import json

from django.http import JsonResponse
from django.views import View

from wagtail_heimdallur.backends import BackendRegistry
from wagtail_heimdallur.conf import get_settings
from wagtail_heimdallur.engines import ProofreadingEngine
from wagtail_heimdallur.exceptions import BackendError
from wagtail_heimdallur.models import ProofreadingResult


class BackendErrorJsonMixin:
    """Render backend errors with a consistent JSON structure."""

    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except BackendError as exc:
            return JsonResponse(
                {
                    "error": {
                        "type": exc.__class__.__name__,
                        "message": str(exc),
                    }
                },
                status=400,
            )

    def _json_body(self) -> dict:
        if not self.request.body:
            return {}

        try:
            return json.loads(self.request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return {}


class ProofreadView(BackendErrorJsonMixin, View):
    """POST endpoint for inline proofreading."""

    engine_class = ProofreadingEngine

    def post(self, request, *args, **kwargs):
        data = self._json_body()
        result = self.engine_class().proofread(
            data.get("text", ""),
            data.get("language", ""),
        )
        return JsonResponse(_proofreading_result_to_dict(result))


class SupportedLanguagesView(BackendErrorJsonMixin, View):
    """GET endpoint exposing available proofreading languages and translation pairs."""

    registry_class = BackendRegistry

    def get(self, request, *args, **kwargs):
        registry = self.registry_class(get_settings())
        return JsonResponse(
            {
                "proofreading": {
                    "languages": registry.get_supported_proofreading_languages(),
                },
                "translation": {
                    "language_pairs": [
                        {
                            "source_language": source_language,
                            "target_language": target_language,
                        }
                        for source_language, target_language
                        in registry.get_supported_translation_pairs()
                    ],
                },
            }
        )


def _proofreading_result_to_dict(result: ProofreadingResult) -> dict:
    return {
        "original_text": result.original_text,
        "corrected_text": result.corrected_text,
        "annotations": [
            annotation.to_dict()
            for annotation in result.annotations
        ],
    }
