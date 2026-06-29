"""Tests for Wagtail hook registration."""

from types import SimpleNamespace

from hypothesis import given, settings
from hypothesis import strategies as st
import pytest
from wagtail.models import Page

from wagtail_heimdallur.hooks import (
    PROOFREAD_CLEAR_FEATURE,
    PROOFREAD_ENTITY_FEATURE,
    PROOFREAD_FEATURE,
    PUBLISH_AND_TRANSLATE_ACTION,
    PublishAndTranslateMenuItem,
    get_hook_registrations,
    handle_publish_and_translate_action,
    register_heimdallur_hooks,
    show_translation_in_progress_message,
)
from wagtail_heimdallur.models import TranslationJob


PROOFREAD_FEATURES = {
    PROOFREAD_FEATURE,
    PROOFREAD_CLEAR_FEATURE,
    PROOFREAD_ENTITY_FEATURE,
}


FEATURE_NAMES = [
    "inline_proofreading",
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
        self.default_features = []
        self.converter_rules = []

    def register_editor_plugin(self, editor_name, feature_name, plugin):
        self.editor_plugins.append((editor_name, feature_name, plugin))

    def register_converter_rule(self, converter_name, feature_name, rule):
        self.converter_rules.append((converter_name, feature_name, rule))


def hook_names_for(features):
    return [
        hook_name
        for hook_name, hook_func
        in get_hook_registrations({"FEATURES": features})
    ]


def expected_hook_names(features):
    names = []
    if features["inline_proofreading"]:
        names.append("register_rich_text_features")
    if features["page_translation"]:
        names.extend(
            [
                "register_admin_urls",
                "register_reports_menu_item",
                "before_edit_page",
                "register_page_action_menu_item",
                "after_edit_page",
                "after_create_page",
            ]
        )
    return names


@given(features=feature_toggle_values)
@settings(max_examples=50)
def test_feature_toggle_conditional_registration(features):
    """Property 2: hooks register only when inline editor features are enabled."""
    merged = {
        "inline_proofreading": True,
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
        "page_translation": True,
        **features,
    }
    if merged["inline_proofreading"]:
        expected_plugins.update(PROOFREAD_FEATURES)

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
            "page_translation": True,
        }
    )
    assert {
        feature_name
        for editor_name, feature_name, plugin in registry.editor_plugins
    } == PROOFREAD_FEATURES
    for feature_name in PROOFREAD_FEATURES:
        assert feature_name in registry.default_features

    plugins = {
        feature_name: plugin
        for editor_name, feature_name, plugin in registry.editor_plugins
    }

    proofread_control = plugins[PROOFREAD_FEATURE]
    assert "wagtail_heimdallur/js/heimdallur.js" in str(proofread_control.media)
    assert "wagtail_heimdallur/css/heimdallur.css" in str(proofread_control.media)

    control_options = {}
    proofread_control.construct_options(control_options)
    assert control_options["controls"] == [{"type": PROOFREAD_FEATURE}]

    entity_options = {}
    plugins[PROOFREAD_ENTITY_FEATURE].construct_options(entity_options)
    assert entity_options["entityTypes"] == [{"type": PROOFREAD_ENTITY_FEATURE}]

    # The highlight entity is stripped on save (keeping its text) via a
    # contentstate converter rule.
    converter_features = {
        feature_name for _, feature_name, _ in registry.converter_rules
    }
    assert PROOFREAD_ENTITY_FEATURE in converter_features


def test_proofread_entity_converter_rule_strips_highlight_but_keeps_text():
    """The save-time converter rule must drop the entity, not its text.

    An unregistered entity would make Wagtail delete the highlighted text on
    save, so the stripping decorator returning its children is load-bearing.
    """
    registry = FeatureRegistryRecorder()
    rich_text_hook = [
        hook_func
        for hook_name, hook_func in get_hook_registrations({})
        if hook_name == "register_rich_text_features"
    ][0]
    rich_text_hook(registry)

    rule = [
        rule
        for converter_name, feature_name, rule in registry.converter_rules
        if feature_name == PROOFREAD_ENTITY_FEATURE
    ][0]
    decorator = rule["to_database_format"]["entity_decorators"][
        PROOFREAD_ENTITY_FEATURE
    ]

    assert decorator({"children": "heimr"}) == "heimr"
    assert rule["from_database_format"] == {}


def test_register_heimdallur_hooks_uses_supplied_register_function():
    registered = []

    def register(hook_name, hook_func):
        registered.append((hook_name, hook_func))

    registrations = register_heimdallur_hooks({}, register=register)

    assert registered == registrations


@pytest.mark.django_db
def test_show_translation_in_progress_message_warns_for_active_target_page(monkeypatch):
    root = Page.get_first_root_node()
    source = Page(title="Source page", slug="source-message")
    target = Page(title="Target page", slug="target-message")
    root.add_child(instance=source)
    root.add_child(instance=target)
    TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
        status=TranslationJob.Status.RUNNING,
    )
    warnings = []

    def warning(request, message):
        warnings.append(str(message))

    monkeypatch.setattr("wagtail_heimdallur.hooks.messages.warning", warning)

    show_translation_in_progress_message(SimpleNamespace(), target)

    assert warnings
    assert "Source page" in warnings[0]
    assert "running" in warnings[0]


@pytest.mark.django_db
def test_show_translation_in_progress_message_warns_for_active_source_page(monkeypatch):
    root = Page.get_first_root_node()
    source = Page(title="Source page", slug="source-origin-message")
    target = Page(title="Target page", slug="target-origin-message")
    root.add_child(instance=source)
    root.add_child(instance=target)
    TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
        status=TranslationJob.Status.QUEUED,
    )
    warnings = []

    def warning(request, message):
        warnings.append(str(message))

    monkeypatch.setattr("wagtail_heimdallur.hooks.messages.warning", warning)

    show_translation_in_progress_message(SimpleNamespace(), source)

    assert warnings
    assert "Target page" in warnings[0]
    assert "queued" in warnings[0]


@pytest.mark.django_db
def test_show_translation_message_prompts_review_of_replaced_edits(monkeypatch):
    root = Page.get_first_root_node()
    source = Page(title="Source page", slug="source-review")
    target = Page(title="Target page", slug="target-review")
    root.add_child(instance=source)
    root.add_child(instance=target)
    TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
        status=TranslationJob.Status.COMPLETED,
        replaced_edits=[{"field_name": "title", "previous": "My edit"}],
    )
    warnings = []
    monkeypatch.setattr(
        "wagtail_heimdallur.hooks.messages.warning",
        lambda request, message: warnings.append(str(message)),
    )

    # has_unpublished_changes gates the review prompt.
    target.has_unpublished_changes = True
    show_translation_in_progress_message(SimpleNamespace(), target)

    assert warnings
    assert "Review the draft" in warnings[0]


@pytest.mark.django_db
def test_publish_and_translate_action_publishes_and_enqueues(monkeypatch):
    from wagtail.models import Locale

    en = Locale.objects.create(language_code="en")
    root = Page.get_first_root_node()
    source = Page(title="Heim", slug="heim-action")
    root.add_child(instance=source)
    target = Page(
        title="Home",
        slug="home-action",
        locale=en,
        translation_key=source.translation_key,
    )
    root.add_child(instance=target)
    # An unpublished draft edit to publish.
    source.title = "Heim 2"
    source.save_revision()

    monkeypatch.setattr(
        "wagtail_heimdallur.hooks.messages.success", lambda request, message: None
    )
    request = SimpleNamespace(POST={PUBLISH_AND_TRANSLATE_ACTION: "1"}, user=None)

    handle_publish_and_translate_action(request, source)

    source.refresh_from_db()
    assert source.title == "Heim 2"  # the draft was published
    assert TranslationJob.objects.filter(
        source_page=source, target_page=target
    ).exists()


@pytest.mark.django_db
def test_publish_and_translate_action_ignored_without_marker():
    root = Page.get_first_root_node()
    source = Page(title="Heim", slug="heim-noaction")
    root.add_child(instance=source)
    request = SimpleNamespace(POST={}, user=None)

    handle_publish_and_translate_action(request, source)

    assert not TranslationJob.objects.exists()


@pytest.mark.django_db
def test_publish_and_translate_menu_item_only_shown_on_source_with_translations():
    from wagtail.models import Locale

    en = Locale.objects.create(language_code="en")
    root = Page.get_first_root_node()
    source = Page(title="Heim", slug="heim-shown")
    root.add_child(instance=source)
    target = Page(
        title="Home",
        slug="home-shown",
        locale=en,
        translation_key=source.translation_key,
    )
    root.add_child(instance=target)

    item = PublishAndTranslateMenuItem()
    assert item.is_shown({"page": source}) is True
    # The translation itself (non-source locale) does not show the action.
    assert item.is_shown({"page": target}) is False
    assert item.is_shown({"page": None}) is False
