"""Page-level translation helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any

from wagtail_heimdallur.engines.translation import TranslationEngine
from wagtail_heimdallur.exceptions import BackendError
from wagtail_heimdallur.models import TranslationJob

logger = logging.getLogger(__name__)


@dataclass
class SkippedField:
    """A field or content segment skipped during page translation."""

    field_name: str
    error: str


@dataclass
class PageTranslationResult:
    """Result of translating a copied page draft."""

    translated_fields: list[str] = field(default_factory=list)
    skipped_fields: list[SkippedField] = field(default_factory=list)

    @property
    def completed_with_warnings(self) -> bool:
        return bool(self.skipped_fields)


class PageTranslationEngine:
    """Translate text content on a copied Wagtail page-like object."""

    def __init__(self, translation_engine: TranslationEngine | None = None):
        self.translation_engine = translation_engine or TranslationEngine()

    def translate_page(
        self,
        source_page: object,
        target_page: object,
        source_language: str | None = None,
        target_language: str | None = None,
    ) -> PageTranslationResult:
        """Translate translatable fields from source_page onto target_page."""
        source_language = source_language or _language_code(source_page)
        target_language = target_language or _language_code(target_page)
        result = PageTranslationResult()

        setattr(target_page, "_heimdallur_translation_in_progress", True)
        try:
            for field_name in _translatable_field_names(source_page):
                original_value = getattr(source_page, field_name, None)
                translated_value, skipped = self._translate_value(
                    original_value,
                    source_language,
                    target_language,
                    field_name,
                )
                if skipped:
                    result.skipped_fields.extend(skipped)
                    if len(skipped) == 1 and skipped[0].field_name == field_name:
                        continue

                setattr(target_page, field_name, translated_value)
                result.translated_fields.append(field_name)

            _save_draft(target_page)
        finally:
            setattr(target_page, "_heimdallur_translation_in_progress", False)

        setattr(
            target_page,
            "_heimdallur_skipped_translation_fields",
            [skipped.field_name for skipped in result.skipped_fields],
        )
        return result

    def _translate_value(
        self,
        value: Any,
        source_language: str,
        target_language: str,
        field_path: str,
    ) -> tuple[Any, list[SkippedField]]:
        if isinstance(value, str):
            if value == "":
                return value, []
            try:
                return (
                    self.translation_engine.translate(
                        value,
                        source_language,
                        target_language,
                    ),
                    [],
                )
            except BackendError as exc:
                logger.exception("Skipping page translation field %s", field_path)
                return value, [SkippedField(field_path, str(exc))]

        if _is_rich_text_like(value):
            translated_source, skipped = self._translate_value(
                value.source,
                source_language,
                target_language,
                field_path,
            )
            if skipped:
                return value, skipped
            return value.__class__(translated_source), []

        if isinstance(value, list):
            translated_items = []
            skipped_fields = []
            for index, item in enumerate(value):
                translated, skipped = self._translate_value(
                    item,
                    source_language,
                    target_language,
                    f"{field_path}.{index}",
                )
                translated_items.append(translated)
                skipped_fields.extend(skipped)
            return translated_items, skipped_fields

        if isinstance(value, tuple):
            translated_items, skipped = self._translate_value(
                list(value),
                source_language,
                target_language,
                field_path,
            )
            return tuple(translated_items), skipped

        if isinstance(value, dict):
            translated_data = {}
            skipped_fields = []
            for key, item in value.items():
                if key == "type":
                    translated_data[key] = item
                    continue

                translated, skipped = self._translate_value(
                    item,
                    source_language,
                    target_language,
                    f"{field_path}.{key}",
                )
                translated_data[key] = translated
                skipped_fields.extend(skipped)
            return translated_data, skipped_fields

        if _is_stream_value_like(value):
            raw_data = value.raw_data
            translated_raw_data, skipped = self._translate_value(
                raw_data,
                source_language,
                target_language,
                field_path,
            )
            if hasattr(value, "stream_block") and hasattr(value.stream_block, "to_python"):
                return value.stream_block.to_python(translated_raw_data), skipped
            return translated_raw_data, skipped

        return value, []


def translate_copied_page(
    source_obj: object,
    target_obj: object,
    engine: PageTranslationEngine | None = None,
) -> PageTranslationResult:
    """Translate a Wagtail object after copy_for_translation has completed."""
    page_engine = engine or PageTranslationEngine()
    return page_engine.translate_page(source_obj, target_obj)


def queue_copied_page_translation(source_obj: object, target_obj: object):
    """Persist a queued translation job for a copied Wagtail object."""
    return TranslationJob.objects.create(
        source_page=source_obj,
        target_page=target_obj,
        source_language=_language_code(source_obj),
        target_language=_language_code(target_obj),
    )


def handle_copy_for_translation_done(sender, source_obj, target_obj, **kwargs):
    """Signal handler for Wagtail's copy_for_translation_done signal."""
    queue_copied_page_translation(source_obj, target_obj)


def connect_page_translation_signal() -> None:
    """Connect page translation to Wagtail's copy_for_translation_done signal."""
    from wagtail.signals import copy_for_translation_done

    copy_for_translation_done.connect(
        handle_copy_for_translation_done,
        dispatch_uid="wagtail_heimdallur.page_translation",
        weak=False,
    )


def _translatable_field_names(page: object) -> list[str]:
    if hasattr(page, "get_translatable_field_names"):
        return list(page.get_translatable_field_names())

    if not hasattr(page, "_meta"):
        return []

    field_names = []
    for model_field in page._meta.get_fields():
        if getattr(model_field, "many_to_many", False) or getattr(
            model_field,
            "one_to_many",
            False,
        ):
            continue

        name = getattr(model_field, "name", None)
        if not name or name in {"id", "pk", "path", "depth", "numchild", "url_path"}:
            continue

        internal_type = ""
        if hasattr(model_field, "get_internal_type"):
            internal_type = model_field.get_internal_type()
        class_name = model_field.__class__.__name__

        if internal_type in {"CharField", "TextField"} or class_name in {
            "RichTextField",
            "StreamField",
        }:
            field_names.append(name)

    return field_names


def _language_code(page: object) -> str:
    locale = getattr(page, "locale", None)
    if locale is not None and hasattr(locale, "language_code"):
        return locale.language_code
    if hasattr(page, "language_code"):
        return page.language_code
    return ""


def _is_rich_text_like(value: Any) -> bool:
    return hasattr(value, "source") and value.__class__.__name__ == "RichText"


def _is_stream_value_like(value: Any) -> bool:
    return hasattr(value, "raw_data")


def _save_draft(page: object) -> None:
    if hasattr(page, "save_revision"):
        page.save_revision()
    elif hasattr(page, "save"):
        page.save()
