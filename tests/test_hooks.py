"""Tests for Wagtail hook registration."""

from hypothesis import given, settings
from hypothesis import strategies as st

from wagtail_heimdallur.hooks import (
    PROOFREAD_FEATURE,
    TRANSLATE_FEATURE,
    get_hook_registrations,
    insert_editor_css,
    insert_editor_js,
    register_heimdallur_hooks,
)


FEATURE_NAMES = [
    "inline_proofreading",
    "inline_translation",
    "page_translation",
]


feature_toggle_values = st.dictionaries(
    st.sampled_from(FEATURE_NAMES),
    st.booleans(),
    max_size=len(FEATURE_NAMES),
)


class FeatureRegistryRecorder:
    def __init__(self):
        self.editor_plugins = []

    def register_editor_plugin(self, editor_name, feature_name, plugin):
        self.editor_plugins.append((editor_name, feature_name, plugin))


def hook_names_for(features):
    return [
        hook_name
        for hook_name, hook_func
        in get_hook_registrations({"FEATURES": features})
    ]


def expected_hook_names(features):
    names = []
    if features["inline_proofreading"] or features["inline_translation"]:
        names.extend(
            [
                "register_rich_text_features",
                "insert_editor_js",
                "insert_editor_css",
            ]
        )
    if features["page_translation"]:
        names.extend(
            [
                "register_admin_urls",
                "register_reports_menu_item",
            ]
        )
    return names


@given(features=feature_toggle_values)
@settings(max_examples=50)
def test_feature_toggle_conditional_registration(features):
    """Property 2: hooks register only when inline editor features are enabled."""
    merged = {
        "inline_proofreading": True,
        "inline_translation": True,
        "page_translation": True,
        **features,
    }
    hook_names = hook_names_for(features)

    assert hook_names == expected_hook_names(merged)


@given(features=feature_toggle_values)
@settings(max_examples=50)
def test_rich_text_feature_registration_matches_enabled_inline_toggles(features):
    """Property 2: rich text controls match enabled inline feature toggles."""
    registrations = get_hook_registrations({"FEATURES": features})
    rich_text_hooks = [
        hook_func
        for hook_name, hook_func in registrations
        if hook_name == "register_rich_text_features"
    ]

    if not rich_text_hooks:
        return

    registry = FeatureRegistryRecorder()
    rich_text_hooks[0](registry)
    plugin_names = {
        feature_name
        for editor_name, feature_name, plugin in registry.editor_plugins
    }
    expected_plugins = set()
    merged = {
        "inline_proofreading": True,
        "inline_translation": True,
        "page_translation": True,
        **features,
    }
    if merged["inline_proofreading"]:
        expected_plugins.add(PROOFREAD_FEATURE)
    if merged["inline_translation"]:
        expected_plugins.add(TRANSLATE_FEATURE)

    assert plugin_names == expected_plugins


def test_feature_toggles_default_to_enabled():
    """Property 3: missing feature toggles default to enabled."""
    registry = FeatureRegistryRecorder()
    registrations = get_hook_registrations({})
    rich_text_hook = [
        hook_func
        for hook_name, hook_func in registrations
        if hook_name == "register_rich_text_features"
    ][0]

    rich_text_hook(registry)

    assert hook_names_for({}) == expected_hook_names(
        {
            "inline_proofreading": True,
            "inline_translation": True,
            "page_translation": True,
        }
    )
    assert {
        feature_name
        for editor_name, feature_name, plugin in registry.editor_plugins
    } == {
        PROOFREAD_FEATURE,
        TRANSLATE_FEATURE,
    }


def test_register_heimdallur_hooks_uses_supplied_register_function():
    registered = []

    def register(hook_name, hook_func):
        registered.append((hook_name, hook_func))

    registrations = register_heimdallur_hooks({}, register=register)

    assert registered == registrations


def test_editor_assets_render_static_tags():
    assert "wagtail_heimdallur/js/heimdallur.js" in insert_editor_js()
    assert "wagtail_heimdallur/css/heimdallur.css" in insert_editor_css()
