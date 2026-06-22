"""Tests for Wagtail-Heimdallur API views."""

import json

import pytest
from django.test import Client, override_settings

from wagtail_heimdallur.exceptions import (
    AuthenticationError,
    BackendError,
    BackendRequestError,
    BackendTimeoutError,
)
from wagtail_heimdallur.models import DiffAnnotation, ProofreadingResult
from wagtail_heimdallur.views import ProofreadView


@pytest.fixture
def api_client():
    with override_settings(ROOT_URLCONF="wagtail_heimdallur.urls"):
        yield Client()


class SuccessfulProofreadingEngine:
    def proofread(self, text, language):
        return ProofreadingResult(
            original_text=text,
            corrected_text=f"{text}!",
            annotations=[
                DiffAnnotation(
                    orig_start_idx=0,
                    orig_end_idx=len(text),
                    orig_string=text,
                    changed_start_idx=0,
                    changed_end_idx=len(text) + 1,
                    changed_string=f"{text}!",
                    change_type="punctuation",
                )
            ],
        )


def post_json(client, path, data):
    return client.post(
        path,
        data=json.dumps(data),
        content_type="application/json",
    )


def test_successful_proofreading_request_response_cycle(api_client, monkeypatch):
    monkeypatch.setattr(ProofreadView, "engine_class", SuccessfulProofreadingEngine)

    response = post_json(
        api_client,
        "/api/heimdallur/proofread/",
        {"text": "halló", "language": "is"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "original_text": "halló",
        "corrected_text": "halló!",
        "annotations": [
            {
                "orig_start_idx": 0,
                "orig_end_idx": 5,
                "orig_string": "halló",
                "changed_start_idx": 0,
                "changed_end_idx": 6,
                "changed_string": "halló!",
                "change_type": "punctuation",
            }
        ],
    }


@pytest.mark.parametrize(
    "error",
    [
        BackendError("generic failure"),
        AuthenticationError("bad credentials"),
        BackendRequestError("bad request"),
        BackendTimeoutError("timeout"),
    ],
)
def test_error_response_format_for_backend_errors(api_client, monkeypatch, error):
    class ErrorEngine:
        def proofread(self, text, language):
            raise error

    monkeypatch.setattr(ProofreadView, "engine_class", ErrorEngine)

    response = post_json(
        api_client,
        "/api/heimdallur/proofread/",
        {"text": "halló", "language": "is"},
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "type": error.__class__.__name__,
            "message": str(error),
        }
    }


@override_settings(
    ROOT_URLCONF="wagtail_heimdallur.urls",
    WAGTAIL_HEIMDALLUR={
        "BACKENDS": {
            "test": {
                "CLASS": "tests.test_backends.fakes.FakeCombinedBackend",
                "OPTIONS": {
                    "proofreading_languages": ["is", "en"],
                    "translation_pairs": [("is", "en"), ("en", "is")],
                },
            },
        },
        "LANGUAGE_ROUTING": {
            "proofreading": {},
            "translation": {},
        },
    },
)
def test_supported_languages_view_returns_correct_structure():
    response = Client().get("/api/heimdallur/languages/")

    assert response.status_code == 200
    assert response.json() == {
        "proofreading": {
            "languages": ["en", "is"],
        },
        "translation": {
            "language_pairs": [
                {"source_language": "en", "target_language": "is"},
                {"source_language": "is", "target_language": "en"},
            ],
        },
    }
