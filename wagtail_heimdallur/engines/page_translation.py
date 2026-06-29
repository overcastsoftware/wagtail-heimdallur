"""Page-level translation helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import logging
from typing import Any

from wagtail_heimdallur.engines.translation import TranslationEngine
from wagtail_heimdallur.exceptions import BackendError
from wagtail_heimdallur.models import TranslationJob

logger = logging.getLogger(__name__)

# Keys in a StreamField block's raw data that are structural, not content, and
# must never be sent for translation (translating a block's UUID would corrupt
# the StreamField).
_NON_TRANSLATABLE_BLOCK_KEYS = frozenset({"type", "id"})


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
    # Blocks re-translated despite a human having edited the prior translation.
    # Informational only (surfaced for review); does not flag the job as a
    # warning the way a skipped/failed segment does.
    replaced_edits: list[dict] = field(default_factory=list)

    @property
    def completed_with_warnings(self) -> bool:
        return bool(self.skipped_fields)


def segment_hash(text: str) -> str:
    """Stable content hash for a translatable text segment."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


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
                translated_value, skipped, translated_count = self._translate_value(
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
                if translated_count:
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

    def collect_texts(self, source_page: object) -> list[str]:
        """Collect page text values in the order they should be translated."""
        texts: list[str] = []
        for field_name in _translatable_field_names(source_page):
            self._collect_texts(
                getattr(source_page, field_name, None),
                texts,
            )
        return texts

    def start_text_translation(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> str:
        """Start async translation for a single text value."""
        return self.translation_engine.start_text_translation(
            text,
            source_language,
            target_language,
        )

    def get_text_translation_status(
        self,
        task_id: str,
        source_language: str,
        target_language: str,
    ):
        """Fetch async text translation status."""
        return self.translation_engine.get_text_translation_status(
            task_id,
            source_language,
            target_language,
        )

    def apply_translated_texts(
        self,
        source_page: object,
        target_page: object,
        translated_texts: list[str],
    ) -> PageTranslationResult:
        """Apply translated text values back onto target_page."""
        translated_texts_iter = iter(translated_texts)
        result = PageTranslationResult()

        setattr(target_page, "_heimdallur_translation_in_progress", True)
        try:
            for field_name in _translatable_field_names(source_page):
                translated_value, translated_count = self._apply_translated_value(
                    getattr(source_page, field_name, None),
                    translated_texts_iter,
                )
                setattr(target_page, field_name, translated_value)
                if translated_count:
                    result.translated_fields.append(field_name)

            try:
                next(translated_texts_iter)
            except StopIteration:
                pass
            else:
                raise BackendError(
                    "Miðeind returned more translated text values than expected."
                )

            _save_draft(target_page)
        finally:
            setattr(target_page, "_heimdallur_translation_in_progress", False)

        setattr(target_page, "_heimdallur_skipped_translation_fields", [])
        return result

    def _translate_value(
        self,
        value: Any,
        source_language: str,
        target_language: str,
        field_path: str,
    ) -> tuple[Any, list[SkippedField], int]:
        if isinstance(value, str):
            if value == "":
                return value, [], 0
            try:
                return (
                    self.translation_engine.translate(
                        value,
                        source_language,
                        target_language,
                    ),
                    [],
                    1,
                )
            except BackendError as exc:
                logger.exception("Skipping page translation field %s", field_path)
                return value, [SkippedField(field_path, str(exc))], 0

        if _is_rich_text_like(value):
            translated_source, skipped, translated_count = self._translate_value(
                value.source,
                source_language,
                target_language,
                field_path,
            )
            if skipped:
                return value, skipped, translated_count
            return value.__class__(translated_source), [], translated_count

        if isinstance(value, list):
            translated_items = []
            skipped_fields = []
            translated_count = 0
            for index, item in enumerate(value):
                translated, skipped, item_translated_count = self._translate_value(
                    item,
                    source_language,
                    target_language,
                    f"{field_path}.{index}",
                )
                translated_items.append(translated)
                skipped_fields.extend(skipped)
                translated_count += item_translated_count
            return translated_items, skipped_fields, translated_count

        if isinstance(value, tuple):
            translated_items, skipped, translated_count = self._translate_value(
                list(value),
                source_language,
                target_language,
                field_path,
            )
            return tuple(translated_items), skipped, translated_count

        if isinstance(value, dict):
            translated_data = {}
            skipped_fields = []
            translated_count = 0
            for key, item in value.items():
                if key in _NON_TRANSLATABLE_BLOCK_KEYS:
                    translated_data[key] = item
                    continue

                translated, skipped, item_translated_count = self._translate_value(
                    item,
                    source_language,
                    target_language,
                    f"{field_path}.{key}",
                )
                translated_data[key] = translated
                skipped_fields.extend(skipped)
                translated_count += item_translated_count
            return translated_data, skipped_fields, translated_count

        if _is_stream_value_like(value):
            if _is_real_stream_value(value):
                skipped_fields: list[SkippedField] = []
                applied_count = [0]

                def _translate_leaf(key, text):
                    try:
                        result = self.translation_engine.translate(
                            text, source_language, target_language
                        )
                    except BackendError as exc:
                        logger.exception(
                            "Skipping page translation field %s", field_path
                        )
                        skipped_fields.append(SkippedField(field_path, str(exc)))
                        return text
                    applied_count[0] += 1
                    return result

                translated_value = self._walk_stream_value(value, _translate_leaf)
                return translated_value, skipped_fields, applied_count[0]

            translated_raw_data, skipped, translated_count = self._translate_value(
                list(value.raw_data),
                source_language,
                target_language,
                field_path,
            )
            if hasattr(value, "stream_block") and hasattr(value.stream_block, "to_python"):
                return (
                    value.stream_block.to_python(translated_raw_data),
                    skipped,
                    translated_count,
                )
            return translated_raw_data, skipped, translated_count

        return value, [], 0

    def _collect_texts(self, value: Any, texts: list[str]) -> None:
        if isinstance(value, str):
            if value:
                texts.append(value)
            return

        if _is_rich_text_like(value):
            self._collect_texts(value.source, texts)
            return

        if isinstance(value, (list, tuple)):
            for item in value:
                self._collect_texts(item, texts)
            return

        if isinstance(value, dict):
            for key, item in value.items():
                if key not in _NON_TRANSLATABLE_BLOCK_KEYS:
                    self._collect_texts(item, texts)
            return

        if _is_stream_value_like(value):
            if _is_real_stream_value(value):
                self._walk_stream_value(
                    value, lambda key, text: (texts.append(text), text)[-1]
                )
            else:
                self._collect_texts(list(value.raw_data), texts)

    def _apply_translated_value(
        self,
        value: Any,
        translated_texts,
    ) -> tuple[Any, int]:
        if isinstance(value, str):
            if value == "":
                return value, 0
            try:
                return next(translated_texts), 1
            except StopIteration as exc:
                raise BackendError(
                    "Miðeind returned fewer translated text values than expected."
                ) from exc

        if _is_rich_text_like(value):
            translated_source, translated_count = self._apply_translated_value(
                value.source,
                translated_texts,
            )
            return value.__class__(translated_source), translated_count

        if isinstance(value, list):
            translated_items = []
            translated_count = 0
            for item in value:
                translated, item_translated_count = self._apply_translated_value(
                    item,
                    translated_texts,
                )
                translated_items.append(translated)
                translated_count += item_translated_count
            return translated_items, translated_count

        if isinstance(value, tuple):
            translated_items, translated_count = self._apply_translated_value(
                list(value),
                translated_texts,
            )
            return tuple(translated_items), translated_count

        if isinstance(value, dict):
            translated_data = {}
            translated_count = 0
            for key, item in value.items():
                if key in _NON_TRANSLATABLE_BLOCK_KEYS:
                    translated_data[key] = item
                    continue
                translated, item_translated_count = self._apply_translated_value(
                    item,
                    translated_texts,
                )
                translated_data[key] = translated
                translated_count += item_translated_count
            return translated_data, translated_count

        if _is_stream_value_like(value):
            if _is_real_stream_value(value):
                applied_count = [0]

                def _take_next(key, _text):
                    try:
                        replacement = next(translated_texts)
                    except StopIteration as exc:
                        raise BackendError(
                            "Miðeind returned fewer translated text values "
                            "than expected."
                        ) from exc
                    applied_count[0] += 1
                    return replacement

                translated_value = self._walk_stream_value(value, _take_next)
                return translated_value, applied_count[0]

            translated_raw_data, translated_count = self._apply_translated_value(
                list(value.raw_data),
                translated_texts,
            )
            if hasattr(value, "stream_block") and hasattr(value.stream_block, "to_python"):
                return value.stream_block.to_python(translated_raw_data), translated_count
            return translated_raw_data, translated_count

        return value, 0

    # ------------------------------------------------------------------
    # Block-aware StreamField traversal.
    #
    # A StreamField is translated by walking its blocks and dispatching on the
    # block *type* — only text-bearing blocks are translated, containers are
    # recursed into, and everything else (choosers, numbers, choices, URLs, ...)
    # is left untouched. ``handle_text`` maps a source string to its replacement;
    # the same walk is shared by collect (record texts) and apply (substitute
    # translations) so the two stay in lock-step.
    # ------------------------------------------------------------------

    def _walk_stream_value(self, stream_value: Any, handle_text, path: str = "") -> Any:
        for child in stream_value:
            child_path = f"{path}:{child.id}" if path else str(child.id)
            child.value = self._walk_stream_block(
                child.block, child.value, handle_text, child_path
            )
        return stream_value

    def _walk_stream_block(
        self, block: Any, value: Any, handle_text, path: str = ""
    ) -> Any:
        from wagtail import blocks
        from wagtail.rich_text import RichText

        # URLBlock/EmailBlock subclass CharBlock but must not be translated.
        if isinstance(block, (blocks.URLBlock, blocks.EmailBlock)):
            return value
        if isinstance(
            block, (blocks.CharBlock, blocks.TextBlock, blocks.BlockQuoteBlock)
        ):
            return (
                handle_text(path, value)
                if isinstance(value, str) and value
                else value
            )
        if isinstance(block, blocks.RawHTMLBlock):
            return handle_text(path, value) if value else value
        if isinstance(block, blocks.RichTextBlock):
            source = getattr(value, "source", None)
            if source is None:
                source = str(value) if value else ""
            return RichText(handle_text(path, source)) if source else value
        if isinstance(block, blocks.StructBlock):
            for name, child_block in block.child_blocks.items():
                value[name] = self._walk_stream_block(
                    child_block, value[name], handle_text, f"{path}:{name}"
                )
            return value
        if isinstance(block, blocks.ListBlock):
            bound_blocks = getattr(value, "bound_blocks", None)
            for idx in range(len(value)):
                # List items carry stable ids; fall back to the index only when a
                # build of Wagtail does not expose them.
                item_id = idx
                if bound_blocks is not None and idx < len(bound_blocks):
                    item_id = getattr(bound_blocks[idx], "id", None) or idx
                value[idx] = self._walk_stream_block(
                    block.child_block, value[idx], handle_text, f"{path}:{item_id}"
                )
            return value
        if isinstance(block, blocks.StreamBlock):
            return self._walk_stream_value(value, handle_text, path)
        return value

    # ------------------------------------------------------------------
    # Segment-keyed walk (incremental translation).
    #
    # ``collect_segments`` / ``apply_resolved_segments`` address every
    # translatable text leaf by a *stable key* — the field name followed by the
    # path of StreamField block ids down to the leaf. Because the key is derived
    # from block ids (which survive edits and reordering) rather than position,
    # a re-translation can match "this block now" to "this block last time" and
    # only re-translate what actually changed.
    # ------------------------------------------------------------------

    def collect_segments(self, page: object) -> list[tuple[str, str]]:
        """Return ``(segment_key, text)`` for every translatable text leaf."""
        segments: list[tuple[str, str]] = []

        def handle(key, text):
            segments.append((key, text))
            return text

        for field_name in _translatable_field_names(page):
            self._walk_value(getattr(page, field_name, None), handle, field_name)
        return segments

    def apply_resolved_segments(
        self,
        source_page: object,
        target_page: object,
        resolved: dict[str, str],
        replaced_edits: list[dict] | None = None,
    ) -> PageTranslationResult:
        """Rebuild target_page's fields from source_page, substituting per key.

        ``resolved`` maps every text segment key to the text to write — a fresh
        translation for changed blocks, or the preserved (possibly hand-edited)
        target text for unchanged ones. The result is saved as a draft revision.
        """
        result = PageTranslationResult(replaced_edits=list(replaced_edits or []))

        setattr(target_page, "_heimdallur_translation_in_progress", True)
        try:
            for field_name in _translatable_field_names(source_page):
                counted = [0]

                def handle(key, text, counted=counted):
                    if key in resolved:
                        counted[0] += 1
                        return resolved[key]
                    return text

                new_value = self._walk_value(
                    getattr(source_page, field_name, None), handle, field_name
                )
                setattr(target_page, field_name, new_value)
                if counted[0]:
                    result.translated_fields.append(field_name)

            _save_draft(target_page)
        finally:
            setattr(target_page, "_heimdallur_translation_in_progress", False)

        setattr(target_page, "_heimdallur_skipped_translation_fields", [])
        return result

    def _walk_value(self, value: Any, handle, path: str) -> Any:
        """Path-aware walk over a single field value (used by the keyed methods).

        ``handle(key, text)`` returns the replacement text for each leaf.
        """
        if isinstance(value, str):
            return handle(path, value) if value else value

        if _is_rich_text_like(value):
            source = value.source or ""
            if not source:
                return value
            return value.__class__(handle(path, source))

        if isinstance(value, list):
            return [
                self._walk_value(item, handle, f"{path}.{index}")
                for index, item in enumerate(value)
            ]

        if isinstance(value, tuple):
            return tuple(
                self._walk_value(item, handle, f"{path}.{index}")
                for index, item in enumerate(value)
            )

        if isinstance(value, dict):
            out = {}
            for key, item in value.items():
                if key in _NON_TRANSLATABLE_BLOCK_KEYS:
                    out[key] = item
                else:
                    out[key] = self._walk_value(item, handle, f"{path}.{key}")
            return out

        if _is_stream_value_like(value):
            if _is_real_stream_value(value):
                return self._walk_stream_value(value, handle, path)
            translated_raw = self._walk_value(list(value.raw_data), handle, path)
            if hasattr(value, "stream_block") and hasattr(
                value.stream_block, "to_python"
            ):
                return value.stream_block.to_python(translated_raw)
            return translated_raw

        return value


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


def queue_update_translation(source_obj: object, target_obj: object):
    """Enqueue an incremental re-translation of an existing target page.

    Unlike the initial copy, this is guarded: it skips unsupported language
    pairs and avoids piling up duplicate work when a job is already in flight.
    """
    source_language = _language_code(source_obj)
    target_language = _language_code(target_obj)
    if not _translation_supported(source_language, target_language):
        return None

    if TranslationJob.objects.filter(
        target_page=target_obj,
        status__in=[
            TranslationJob.Status.QUEUED,
            TranslationJob.Status.RUNNING,
        ],
    ).exists():
        return None

    return TranslationJob.objects.create(
        source_page=source_obj,
        target_page=target_obj,
        source_language=source_language,
        target_language=target_language,
    )


def handle_copy_for_translation_done(sender, source_obj, target_obj, **kwargs):
    """Signal handler for Wagtail's copy_for_translation_done signal."""
    queue_copied_page_translation(source_obj, target_obj)


def enqueue_translation_updates(source_obj: object) -> list:
    """Queue incremental re-translation of a page's existing translations.

    Used by the deliberate "Publish & update translations" page action — the
    page being acted on is the source, and each of its translations re-translates
    only the blocks whose source changed.
    """
    get_translations = getattr(source_obj, "get_translations", None)
    if get_translations is None:
        return []

    source = getattr(source_obj, "specific", source_obj)
    jobs = []
    for translation in get_translations(inclusive=False):
        job = queue_update_translation(
            source, getattr(translation, "specific", translation)
        )
        if job is not None:
            jobs.append(job)
    return jobs


def page_has_translation_targets(page: object) -> bool:
    """Whether a page has translations that a configured backend can update."""
    get_translations = getattr(page, "get_translations", None)
    if get_translations is None:
        return False
    source_language = _language_code(page)
    try:
        translations = list(get_translations(inclusive=False))
    except Exception:  # pragma: no cover - defensive
        return False
    return any(
        _translation_supported(source_language, _language_code(translation))
        for translation in translations
    )


def connect_page_translation_signal() -> None:
    """Connect the initial translation to Wagtail's copy_for_translation signal.

    Re-translation after edits is triggered deliberately from the page action
    menu (see the "Publish & update translations" hook), not automatically on
    every publish.
    """
    from wagtail.signals import copy_for_translation_done

    copy_for_translation_done.connect(
        handle_copy_for_translation_done,
        dispatch_uid="wagtail_heimdallur.page_translation",
        weak=False,
    )


def _translation_supported(source_language: str, target_language: str) -> bool:
    if (
        not source_language
        or not target_language
        or source_language == target_language
    ):
        return False
    from wagtail_heimdallur.backends.registry import BackendRegistry
    from wagtail_heimdallur.conf import get_settings

    try:
        BackendRegistry(get_settings()).get_backend_for_translation(
            source_language, target_language
        )
    except Exception:
        return False
    return True


def _is_source_locale(instance: object, config: dict) -> bool:
    locale = getattr(instance, "locale", None)
    source_locales = config.get("source_locales")
    if source_locales:
        code = getattr(locale, "language_code", None)
        return code in source_locales

    # Default: only the site's default locale is a translation source.
    if locale is None:
        return False
    from wagtail.models import Locale

    try:
        default_locale = Locale.get_default()
    except Exception:
        return False
    return getattr(locale, "pk", None) == default_locale.pk


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


def _is_real_stream_value(value: Any) -> bool:
    """A real Wagtail StreamValue (whose blocks can be walked by type), as
    opposed to a plain raw-data list used in tests."""
    stream_block = getattr(value, "stream_block", None)
    return stream_block is not None and hasattr(stream_block, "child_blocks")


def _save_draft(page: object) -> None:
    if hasattr(page, "save_revision"):
        page.save_revision()
    elif hasattr(page, "save"):
        page.save()
