"""Shared test fixtures and configuration for wagtail_heimdallur tests."""

import django
from django.conf import settings

from wagtail_heimdallur.backends.base import (
    BaseProofreadingBackend,
    BaseTranslationBackend,
)


def pytest_configure(config):
    """Configure Django settings for test runs if not already configured."""
    if not settings.configured:
        settings.configure(
            SECRET_KEY="test-secret-key-not-for-production",
            INSTALLED_APPS=[
                "django.contrib.contenttypes",
                "django.contrib.auth",
            ],
            DATABASES={
                "default": {
                    "ENGINE": "django.db.backends.sqlite3",
                    "NAME": ":memory:",
                }
            },
            USE_TZ=True,
            WAGTAIL_HEIMDALLUR={
                "FEATURES": {
                    "inline_proofreading": True,
                    "page_translation": True,
                },
                "BACKENDS": {
                    "test": {
                        "CLASS": "tests.conftest.DummyBackend",
                        "OPTIONS": {},
                        "enabled": True,
                    },
                },
                "LANGUAGE_ROUTING": {
                    "proofreading": {},
                    "translation": {},
                },
            },
        )
        django.setup()

class DummyBackend(BaseProofreadingBackend, BaseTranslationBackend):
    """A minimal backend for testing purposes."""

    def __init__(self, **kwargs):
        self.options = kwargs

    def proofread(self, text: str, language: str):
        from wagtail_heimdallur.models import ProofreadingResult

        return ProofreadingResult(
            original_text=text, corrected_text=text, annotations=[]
        )

    def translate(self, text: str, source_language: str, target_language: str) -> str:
        return text

    def get_supported_languages(self) -> list:
        return ["is", "en"]

    def get_supported_language_pairs(self) -> list:
        return [("is", "en"), ("en", "is")]
