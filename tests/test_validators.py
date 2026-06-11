"""Tests for WAGTAIL_HEIMDALLUR configuration validation."""

import pytest
from django.core.exceptions import ImproperlyConfigured
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from wagtail_heimdallur.validators import ConfigurationValidator


VALID_BACKEND_CLASS = "tests.test_backends.fakes.FakeCombinedBackend"
VALID_BACKENDS = {
    "valid": {
        "CLASS": VALID_BACKEND_CLASS,
        "OPTIONS": {},
    },
}
VALID_FEATURES = {
    "inline_proofreading",
    "inline_translation",
    "page_translation",
}


feature_names = st.text(
    alphabet=st.characters(min_codepoint=97, max_codepoint=122) | st.just("_"),
    min_size=1,
    max_size=30,
)
backend_ids = st.text(
    alphabet=st.characters(min_codepoint=97, max_codepoint=122) | st.just("_"),
    min_size=1,
    max_size=20,
)
language_codes = st.text(
    alphabet=st.characters(min_codepoint=97, max_codepoint=122),
    min_size=2,
    max_size=5,
)
language_pairs = st.tuples(language_codes, language_codes).filter(
    lambda pair: pair[0] != pair[1]
)


def settings_dict(backends=None, features=None, routing=None):
    return {
        "BACKENDS": backends if backends is not None else VALID_BACKENDS,
        "FEATURES": features or {},
        "LANGUAGE_ROUTING": routing or {"proofreading": {}, "translation": {}},
    }


def test_valid_configuration_passes_validation():
    ConfigurationValidator().validate(settings_dict())


def test_no_backends_configured_raises_improperly_configured():
    with pytest.raises(ImproperlyConfigured):
        ConfigurationValidator().validate(settings_dict(backends={}))


def test_missing_backend_class_raises_improperly_configured():
    with pytest.raises(ImproperlyConfigured):
        ConfigurationValidator().validate(
            settings_dict(backends={"broken": {"OPTIONS": {}}})
        )


def test_unimportable_backend_class_raises_improperly_configured():
    with pytest.raises(ImproperlyConfigured):
        ConfigurationValidator().validate(
            settings_dict(
                backends={
                    "broken": {
                        "CLASS": "tests.test_backends.fakes.DoesNotExist",
                        "OPTIONS": {},
                    },
                }
            )
        )


@given(
    invalid_backend=backend_ids,
    language=language_codes,
    pair=language_pairs,
)
@settings(max_examples=50)
def test_invalid_backend_references_in_routing_rejected(
    invalid_backend,
    language,
    pair,
):
    """Property 7: routing may only reference configured backend identifiers."""
    assume(invalid_backend not in VALID_BACKENDS)
    validator = ConfigurationValidator()

    with pytest.raises(ImproperlyConfigured):
        validator.validate(
            settings_dict(
                routing={
                    "proofreading": {language: invalid_backend},
                    "translation": {},
                }
            )
        )

    with pytest.raises(ImproperlyConfigured):
        validator.validate(
            settings_dict(
                routing={
                    "proofreading": {},
                    "translation": {pair: invalid_backend},
                }
            )
        )


@given(invalid_feature=feature_names)
@settings(max_examples=50)
def test_unrecognized_feature_names_rejected(invalid_feature):
    """Property 8: feature toggles must use recognized feature names."""
    assume(invalid_feature not in VALID_FEATURES)

    with pytest.raises(ImproperlyConfigured):
        ConfigurationValidator().validate(
            settings_dict(features={invalid_feature: True})
        )
