"""Wagtail hook registration for Wagtail-Heimdallur."""

from __future__ import annotations

from collections.abc import Callable

from django.urls import include, path, reverse
from django.utils.translation import gettext_lazy as _
from django.templatetags.static import static
from django.utils.html import format_html
from wagtail import hooks as wagtail_hooks
from wagtail.admin.menu import AdminOnlyMenuItem

from wagtail_heimdallur.conf import DEFAULTS
from wagtail_heimdallur.engines.page_translation import connect_page_translation_signal

PROOFREAD_FEATURE = "heimdallur-proofread"
TRANSLATE_FEATURE = "heimdallur-translate"
EDITOR_JS_PATH = "wagtail_heimdallur/js/heimdallur.js"
EDITOR_CSS_PATH = "wagtail_heimdallur/css/heimdallur.css"


def register_heimdallur_hooks(
    settings: dict,
    register: Callable | None = None,
) -> list[tuple[str, Callable]]:
    """Register Wagtail hooks for enabled Heimdallur features."""
    register = register or wagtail_hooks.register
    registrations = get_hook_registrations(settings)

    for hook_name, hook_func in registrations:
        register(hook_name, hook_func)

    if _feature_settings(settings)["page_translation"]:
        connect_page_translation_signal()

    return registrations


def get_hook_registrations(settings: dict) -> list[tuple[str, Callable]]:
    """Return hook registrations required by the enabled feature toggles."""
    features = _feature_settings(settings)
    registrations = []

    if _inline_editor_enabled(features):
        registrations.extend(
            [
                (
                    "register_rich_text_features",
                    _build_register_rich_text_features_hook(features),
                ),
                ("insert_editor_js", insert_editor_js),
                ("insert_editor_css", insert_editor_css),
            ]
        )

    if features["page_translation"]:
        registrations.extend(
            [
                ("register_admin_urls", register_translation_queue_admin_urls),
                (
                    "register_reports_menu_item",
                    register_translation_queue_report_menu_item,
                ),
            ]
        )

    return registrations


def insert_editor_js() -> str:
    """Load the compiled Heimdallur editor bundle in Wagtail admin."""
    return format_html(
        '<script src="{}"></script>',
        static(EDITOR_JS_PATH),
    )


def insert_editor_css() -> str:
    """Load Heimdallur editor styles in Wagtail admin."""
    return format_html(
        '<link rel="stylesheet" href="{}">',
        static(EDITOR_CSS_PATH),
    )


def register_translation_queue_admin_urls():
    """Register Wagtail admin URLs for Heimdallur reports."""
    return [
        path(
            "heimdallur/",
            include(
                "wagtail_heimdallur.admin_urls",
                namespace="wagtail_heimdallur_admin",
            ),
        ),
    ]


def register_translation_queue_report_menu_item():
    """Add the translation queue report to Wagtail's Reports menu."""
    return AdminOnlyMenuItem(
        _("Translation queue"),
        reverse("wagtail_heimdallur_admin:translation_queue"),
        name="heimdallur-translation-queue",
        icon_name="tasks",
        order=1250,
    )


def _build_register_rich_text_features_hook(features: dict) -> Callable:
    def register_rich_text_features(feature_registry) -> None:
        if features["inline_proofreading"]:
            _register_draftail_control(
                feature_registry,
                PROOFREAD_FEATURE,
                "Proofread",
            )

        if features["inline_translation"]:
            _register_draftail_control(
                feature_registry,
                TRANSLATE_FEATURE,
                "Translate",
            )

    return register_rich_text_features


def _register_draftail_control(feature_registry, feature_name: str, label: str) -> None:
    from wagtail.admin.rich_text.editors.draftail.features import ControlFeature

    feature_registry.register_editor_plugin(
        "draftail",
        feature_name,
        ControlFeature(
            {
                "type": feature_name,
                "label": label,
                "description": label,
            }
        ),
    )


def _feature_settings(settings: dict) -> dict:
    return {
        **DEFAULTS["FEATURES"],
        **settings.get("FEATURES", {}),
    }


def _inline_editor_enabled(features: dict) -> bool:
    return features["inline_proofreading"] or features["inline_translation"]
