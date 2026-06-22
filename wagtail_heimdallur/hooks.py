"""Wagtail hook registration for Wagtail-Heimdallur."""

from __future__ import annotations

from collections.abc import Callable

from django.contrib import messages
from django.urls import include, path, reverse
from django.urls.exceptions import NoReverseMatch
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from wagtail import hooks as wagtail_hooks
from wagtail.admin.menu import AdminOnlyMenuItem

from wagtail_heimdallur.conf import DEFAULTS
from wagtail_heimdallur.engines.page_translation import connect_page_translation_signal
from wagtail_heimdallur.models import TranslationJob

PROOFREAD_FEATURE = "heimdallur-proofread"
PROOFREAD_CLEAR_FEATURE = "heimdallur-proofread-clear"
PROOFREAD_ENTITY_FEATURE = "HEIMDALLUR_PROOFREAD"
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

    if features["inline_proofreading"]:
        # The Draftail feature media loads the editor JS/CSS where it is used,
        # so no global asset hooks are needed.
        registrations.append(
            (
                "register_rich_text_features",
                _build_register_rich_text_features_hook(),
            )
        )

    if features["page_translation"]:
        registrations.extend(
            [
                ("register_admin_urls", register_translation_queue_admin_urls),
                (
                    "register_reports_menu_item",
                    register_translation_queue_report_menu_item,
                ),
                ("before_edit_page", show_translation_in_progress_message),
            ]
        )

    return registrations


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


def show_translation_in_progress_message(request, page):
    """Show an admin message when the edited page has active translation work."""
    target_job = (
        TranslationJob.objects.filter(
            target_page_id=page.id,
            status__in=[
                TranslationJob.Status.QUEUED,
                TranslationJob.Status.RUNNING,
            ],
        )
        .select_related("source_page")
        .order_by("-created_at")
        .first()
    )
    source_job = (
        TranslationJob.objects.filter(
            source_page_id=page.id,
            status__in=[
                TranslationJob.Status.QUEUED,
                TranslationJob.Status.RUNNING,
            ],
        )
        .select_related("target_page")
        .order_by("-created_at")
        .first()
    )

    queue_url = _translation_queue_url()
    if target_job is not None:
        messages.warning(
            request,
            _with_queue_link(
                _target_translation_message(target_job),
                queue_url,
            ),
        )
    if source_job is not None:
        messages.warning(
            request,
            _with_queue_link(
                _source_translation_message(source_job),
                queue_url,
            ),
        )
    return None


def _translation_queue_url() -> str:
    try:
        return reverse("wagtail_heimdallur_admin:translation_queue")
    except (AttributeError, NoReverseMatch):
        return ""


def _with_queue_link(message, queue_url: str):
    if not queue_url:
        return message

    return format_html(
        '{} <a href="{}">{}</a>',
        message,
        queue_url,
        _("View translation queue"),
    )


def _target_translation_message(job: TranslationJob):
    return format_html(
        '{} "{}" {}.',
        _("This page is being translated from"),
        job.source_page.title,
        job.get_status_display().lower(),
    )


def _source_translation_message(job: TranslationJob):
    return format_html(
        '{} "{}" {}.',
        _("This page has an active translation targeting"),
        job.target_page.title,
        job.get_status_display().lower(),
    )


def _build_register_rich_text_features_hook() -> Callable:
    def register_rich_text_features(feature_registry) -> None:
        _register_draftail_proofread_feature(feature_registry)

    return register_rich_text_features


def _register_draftail_proofread_feature(feature_registry) -> None:
    """Register proofreading as a Draftail plugin (toolbar controls + entity).

    The ``HEIMDALLUR_PROOFREAD`` entity highlights are ephemeral review aids:
    a contentstate converter rule strips the entity on save while preserving
    its text. (Leaving the entity unregistered would make Wagtail delete the
    highlighted text entirely, so the stripping rule is required.)
    """
    from wagtail.admin.rich_text.editors.draftail.features import (
        ControlFeature,
        EntityFeature,
    )

    media = {
        "js": [EDITOR_JS_PATH],
        "css": {"all": [EDITOR_CSS_PATH]},
    }

    feature_registry.register_editor_plugin(
        "draftail",
        PROOFREAD_FEATURE,
        ControlFeature({"type": PROOFREAD_FEATURE}, **media),
    )
    feature_registry.register_editor_plugin(
        "draftail",
        PROOFREAD_CLEAR_FEATURE,
        ControlFeature({"type": PROOFREAD_CLEAR_FEATURE}, **media),
    )
    feature_registry.register_editor_plugin(
        "draftail",
        PROOFREAD_ENTITY_FEATURE,
        EntityFeature({"type": PROOFREAD_ENTITY_FEATURE}, **media),
    )
    feature_registry.register_converter_rule(
        "contentstate",
        PROOFREAD_ENTITY_FEATURE,
        {
            "from_database_format": {},
            "to_database_format": {
                "entity_decorators": {
                    PROOFREAD_ENTITY_FEATURE: _strip_proofread_entity,
                },
            },
        },
    )

    for feature_name in (
        PROOFREAD_FEATURE,
        PROOFREAD_CLEAR_FEATURE,
        PROOFREAD_ENTITY_FEATURE,
    ):
        _add_default_feature(feature_registry, feature_name)


def _strip_proofread_entity(props):
    """Drop a proofreading highlight entity on save, keeping its text."""
    return props["children"]


def _add_default_feature(feature_registry, feature_name: str) -> None:
    default_features = getattr(feature_registry, "default_features", None)
    if default_features is not None and feature_name not in default_features:
        default_features.append(feature_name)


def _feature_settings(settings: dict) -> dict:
    return {
        **DEFAULTS["FEATURES"],
        **settings.get("FEATURES", {}),
    }
