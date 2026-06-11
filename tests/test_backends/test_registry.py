"""Property-based tests for backend registry routing."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from wagtail_heimdallur.backends import (
    BackendRegistry,
    BaseProofreadingBackend,
    BaseTranslationBackend,
)
from wagtail_heimdallur.exceptions import (
    NoAvailableBackendError,
    UnsupportedLanguageError,
)
from tests.test_backends.fakes import OptionCaptureBackend


COMBINED_BACKEND = "tests.test_backends.fakes.FakeCombinedBackend"


language_codes = st.text(
    alphabet=st.characters(min_codepoint=97, max_codepoint=122),
    min_size=2,
    max_size=5,
)
language_pairs = st.tuples(language_codes, language_codes).filter(
    lambda pair: pair[0] != pair[1]
)
jsonish_values = st.recursive(
    st.none()
    | st.booleans()
    | st.integers(min_value=-1000, max_value=1000)
    | st.text(max_size=20),
    lambda children: st.lists(children, max_size=3)
    | st.dictionaries(st.text(min_size=1, max_size=10), children, max_size=3),
    max_leaves=10,
)


def registry_settings(backends, routing=None):
    return {
        "BACKENDS": backends,
        "LANGUAGE_ROUTING": routing or {"proofreading": {}, "translation": {}},
    }


def backend_config(
    label,
    proofreading_languages=None,
    translation_pairs=None,
    enabled=True,
    **options,
):
    return {
        "CLASS": COMBINED_BACKEND,
        "OPTIONS": {
            "label": label,
            "proofreading_languages": list(proofreading_languages or []),
            "translation_pairs": list(translation_pairs or []),
            **options,
        },
        "enabled": enabled,
    }


@given(language=language_codes)
@settings(max_examples=50)
def test_proofreading_language_routing_resolution(language):
    """Property 4: explicit proofreading routes resolve to the configured backend."""
    registry = BackendRegistry(
        registry_settings(
            {
                "first": backend_config("first", proofreading_languages=[language]),
                "second": backend_config("second", proofreading_languages=[language]),
            },
            routing={
                "proofreading": {language: "second"},
                "translation": {},
            },
        )
    )

    backend = registry.get_backend_for_proofreading(language)

    assert isinstance(backend, BaseProofreadingBackend)
    assert backend.label == "second"


@given(pair=language_pairs)
@settings(max_examples=50)
def test_translation_language_pair_routing_resolution(pair):
    """Property 5: explicit translation routes resolve to the configured backend."""
    registry = BackendRegistry(
        registry_settings(
            {
                "first": backend_config("first", translation_pairs=[pair]),
                "second": backend_config("second", translation_pairs=[pair]),
            },
            routing={
                "proofreading": {},
                "translation": {pair: "second"},
            },
        )
    )

    backend = registry.get_backend_for_translation(*pair)

    assert isinstance(backend, BaseTranslationBackend)
    assert backend.label == "second"


@given(language=language_codes, pair=language_pairs)
@settings(max_examples=50)
def test_routing_fallback_to_first_capable_backend(language, pair):
    """Property 6: fallback chooses the first capable enabled backend."""
    registry = BackendRegistry(
        registry_settings(
            {
                "unsupported": backend_config("unsupported"),
                "first": backend_config(
                    "first",
                    proofreading_languages=[language],
                    translation_pairs=[pair],
                ),
                "second": backend_config(
                    "second",
                    proofreading_languages=[language],
                    translation_pairs=[pair],
                ),
            }
        )
    )

    proofreading_backend = registry.get_backend_for_proofreading(language)
    translation_backend = registry.get_backend_for_translation(*pair)

    assert proofreading_backend.label == "first"
    assert translation_backend.label == "first"


@given(language=language_codes, pair=language_pairs)
@settings(max_examples=50)
def test_unsupported_language_raises_error(language, pair):
    """Property 10: unsupported languages and pairs raise UnsupportedLanguageError."""
    unsupported_language = f"{language}x"
    unsupported_pair = (pair[0], f"{pair[1]}x")
    registry = BackendRegistry(
        registry_settings(
            {
                "backend": backend_config(
                    "backend",
                    proofreading_languages=[language],
                    translation_pairs=[pair],
                ),
            }
        )
    )

    with pytest.raises(UnsupportedLanguageError):
        registry.get_backend_for_proofreading(unsupported_language)

    with pytest.raises(UnsupportedLanguageError):
        registry.get_backend_for_translation(*unsupported_pair)


@given(language=language_codes, pair=language_pairs)
@settings(max_examples=50)
def test_disabled_backends_excluded_from_routing(language, pair):
    """Property 17: disabled backends are not returned from routing."""
    registry = BackendRegistry(
        registry_settings(
            {
                "disabled": backend_config(
                    "disabled",
                    proofreading_languages=[language],
                    translation_pairs=[pair],
                    enabled=False,
                ),
                "enabled": backend_config(
                    "enabled",
                    proofreading_languages=[language],
                    translation_pairs=[pair],
                    enabled=True,
                ),
            },
            routing={
                "proofreading": {language: "disabled"},
                "translation": {pair: "disabled"},
            },
        )
    )

    proofreading_backend = registry.get_backend_for_proofreading(language)
    translation_backend = registry.get_backend_for_translation(*pair)

    assert proofreading_backend.label == "enabled"
    assert translation_backend.label == "enabled"


@given(language=language_codes, pair=language_pairs)
@settings(max_examples=50)
def test_all_capable_backends_disabled_raise_no_available(language, pair):
    """Property 18: all capable disabled backends raise NoAvailableBackendError."""
    registry = BackendRegistry(
        registry_settings(
            {
                "disabled": backend_config(
                    "disabled",
                    proofreading_languages=[language],
                    translation_pairs=[pair],
                    enabled=False,
                ),
            }
        )
    )

    with pytest.raises(NoAvailableBackendError):
        registry.get_backend_for_proofreading(language)

    with pytest.raises(NoAvailableBackendError):
        registry.get_backend_for_translation(*pair)


@given(options=st.dictionaries(st.text(min_size=1, max_size=12), jsonish_values, max_size=6))
@settings(max_examples=50)
def test_backend_options_pass_through(options):
    """Property 9: backend OPTIONS are passed through as constructor kwargs."""
    OptionCaptureBackend.last_options = None
    registry = BackendRegistry(
        registry_settings(
            {
                "capture": {
                    "CLASS": "tests.test_backends.fakes.OptionCaptureBackend",
                    "OPTIONS": options,
                    "enabled": True,
                },
            }
        )
    )

    assert "capture" in registry._backends
    assert OptionCaptureBackend.last_options == options
