"""Page-level translation helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
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
    # Non-text segment memory written during apply: {key: (source_hash, written_hash)},
    # and the set of non-text keys seen (so the queue can persist/prune them).
    nontext_updates: dict = field(default_factory=dict)
    nontext_keys: set = field(default_factory=set)

    @property
    def completed_with_warnings(self) -> bool:
        return bool(self.skipped_fields)


# Sentinel for "this non-text block does not exist on the target".
_MISSING = object()


def segment_hash(text: str) -> str:
    """Stable content hash for a translatable text segment."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


class PageTranslationEngine:
    """Translate text content on a copied Wagtail page-like object."""

    def __init__(self, translation_engine: TranslationEngine | None = None):
        self.translation_engine = translation_engine or TranslationEngine()
        self._untranslatable_block_classes: tuple | None = None
        self._untranslatable_fields: set | None = None
        self._child_relation_config: dict | None = None
        self._warned_child_relations: set = set()

    def _field_names(self, page: object) -> list[str]:
        """Translatable page field names, minus any configured exclusions."""
        excluded = self._untranslatable_field_names()
        return [n for n in _translatable_field_names(page) if n not in excluded]

    def _untranslatable_field_names(self) -> set:
        if self._untranslatable_fields is None:
            from wagtail_heimdallur.conf import get_settings

            self._untranslatable_fields = set(
                get_settings()
                .get("PAGE_TRANSLATION", {})
                .get("untranslatable_fields", [])
            )
        return self._untranslatable_fields

    def _child_relations(self) -> dict:
        if self._child_relation_config is None:
            from wagtail_heimdallur.conf import get_settings

            self._child_relation_config = dict(
                get_settings()
                .get("PAGE_TRANSLATION", {})
                .get("translatable_child_relations", {})
            )
        return self._child_relation_config

    @staticmethod
    def _child_segment_ref(child) -> str | None:
        """The child's translation_key, or None if it isn't a TranslatableMixin.

        A TranslatableMixin child keeps the same translation_key across locales
        (copy_for_translation copies it), so source and target match by it
        regardless of order. Children without one can't be matched reliably and
        are skipped — position matching would silently mis-apply translations
        when fields are reordered/added/removed.
        """
        translation_key = getattr(child, "translation_key", None)
        return str(translation_key) if translation_key else None

    def _warn_child_relation_not_translatable(self, relation: str) -> None:
        if relation not in self._warned_child_relations:
            self._warned_child_relations.add(relation)
            logger.warning(
                "Heimdallur: child relation %r is configured for translation but "
                "its model is not a TranslatableMixin (no translation_key); "
                "skipping. Add TranslatableMixin to the child model to translate it.",
                relation,
            )

    def _collect_child_segments(self, page: object, handle) -> None:
        """Record translatable text on configured child relations (form fields, …)."""
        for relation, fields in self._child_relations().items():
            manager = getattr(page, relation, None)
            if manager is None:
                continue
            try:
                children = list(manager.all())
            except Exception:  # pragma: no cover - defensive
                continue
            for child in children:
                ref = self._child_segment_ref(child)
                if ref is None:
                    self._warn_child_relation_not_translatable(relation)
                    break  # all children share a model, so skip the whole relation
                for field in fields:
                    text = getattr(child, field, "") or ""
                    if isinstance(text, str) and text:
                        handle(f"{relation}:{ref}:{field}", text)

    def _apply_child_segments(self, target_page, resolved, result) -> None:
        """Write translated text back onto the target's child objects (by position)."""
        for relation, fields in self._child_relations().items():
            manager = getattr(target_page, relation, None)
            if manager is None:
                continue
            try:
                children = list(manager.all())
            except Exception:  # pragma: no cover - defensive
                continue
            if not children:
                continue
            changed = False
            for child in children:
                ref = self._child_segment_ref(child)
                if ref is None:
                    break
                for field in fields:
                    key = f"{relation}:{ref}:{field}"
                    if key in resolved:
                        setattr(child, field, resolved[key])
                        changed = True
            if changed:
                # In-place edits to `.all()` children are not serialized on save;
                # re-setting the relation is what persists them.
                manager.set(children, bulk=False)
                if relation not in result.translated_fields:
                    result.translated_fields.append(relation)

    def _excluded_block_classes(self) -> tuple:
        """Block classes configured (or defaulted) to skip translation."""
        if self._untranslatable_block_classes is None:
            from django.utils.module_loading import import_string

            from wagtail_heimdallur.conf import get_settings

            paths = (
                get_settings()
                .get("PAGE_TRANSLATION", {})
                .get("untranslatable_blocks", [])
            )
            classes = []
            for path in paths:
                try:
                    classes.append(import_string(path))
                except ImportError:
                    logger.warning(
                        "Heimdallur: could not import untranslatable block %r", path
                    )
            self._untranslatable_block_classes = tuple(classes)
        return self._untranslatable_block_classes

    def _block_translatable(self, block: Any) -> bool:
        """Whether a text-bearing block should be machine translated.

        Honors a ``translatable = False`` attribute on the block and the
        configured ``untranslatable_blocks`` list. Non-translatable blocks are
        treated as non-text content (synced from source / overridable).
        """
        if getattr(block, "translatable", True) is False:
            return False
        excluded = self._excluded_block_classes()
        return not (excluded and isinstance(block, excluded))

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

    def _walk_stream_value(
        self,
        stream_value: Any,
        handle_text,
        path: str = "",
        handle_value=None,
        mutate: bool = True,
    ) -> Any:
        for child in stream_value:
            child_path = f"{path}:{child.id}" if path else str(child.id)
            new_value = self._walk_stream_block(
                child.block, child.value, handle_text, child_path, handle_value, mutate
            )
            if mutate:
                child.value = new_value
        return stream_value

    def _walk_stream_block(
        self,
        block: Any,
        value: Any,
        handle_text,
        path: str = "",
        handle_value=None,
        mutate: bool = True,
    ) -> Any:
        from wagtail import blocks
        from wagtail.rich_text import RichText

        def as_nontext():
            return handle_value(path, block, value) if handle_value else value

        # URLBlock/EmailBlock subclass CharBlock but must not be translated — they
        # are non-text leaves (e.g. EmbedBlock subclasses URLBlock).
        if isinstance(block, (blocks.URLBlock, blocks.EmailBlock)):
            return as_nontext()
        if isinstance(
            block,
            (
                blocks.CharBlock,
                blocks.TextBlock,
                blocks.BlockQuoteBlock,
                blocks.RawHTMLBlock,
            ),
        ):
            if self._block_translatable(block) and isinstance(value, str) and value:
                return handle_text(path, value)
            return as_nontext()
        if isinstance(block, blocks.RichTextBlock):
            source = getattr(value, "source", None)
            if source is None:
                source = str(value) if value else ""
            if self._block_translatable(block) and source:
                return RichText(handle_text(path, source))
            return as_nontext()
        if isinstance(block, blocks.StructBlock):
            for name, child_block in block.child_blocks.items():
                new_value = self._walk_stream_block(
                    child_block,
                    value[name],
                    handle_text,
                    f"{path}:{name}",
                    handle_value,
                    mutate,
                )
                if mutate:
                    value[name] = new_value
            return value
        if isinstance(block, blocks.ListBlock):
            # List items carry stable, persisted ids — key by them so a re-translation
            # can tell which item is which across edits and reordering. The read-only
            # walk (mutate=False, used by collect) must NOT reassign here: Wagtail's
            # ListValue.__setitem__ mints a fresh id, which would corrupt the source's
            # ids before the apply pass reads them.
            bound_blocks = getattr(value, "bound_blocks", None)
            for idx in range(len(value)):
                item_id = idx
                if bound_blocks is not None and idx < len(bound_blocks):
                    item_id = getattr(bound_blocks[idx], "id", None) or idx
                new_value = self._walk_stream_block(
                    block.child_block,
                    value[idx],
                    handle_text,
                    f"{path}:{item_id}",
                    handle_value,
                    mutate,
                )
                if mutate:
                    value[idx] = new_value
            return value
        if isinstance(block, blocks.StreamBlock):
            return self._walk_stream_value(value, handle_text, path, handle_value, mutate)
        # Any other terminal block (chooser, number, boolean, choice, …) is a
        # non-text leaf.
        return as_nontext()

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

        for field_name in self._field_names(page):
            self._walk_value(
                getattr(page, field_name, None), handle, field_name, mutate=False
            )
        self._collect_child_segments(page, handle)
        return segments

    # ------------------------------------------------------------------
    # Non-text leaves (choosers, embeds, numbers, …).
    #
    # These are not translated. By default they follow the source, but a
    # translator can deliberately override one per locale (e.g. a localized
    # video in an EmbedBlock). The override is *sticky*: once a block diverges
    # from the value we last wrote, it is left alone on every future
    # re-translation, while un-overridden blocks keep syncing from the source.
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_block_value(block: Any, value: Any) -> str | None:
        """Stable hash of a non-text block value, or None if it can't be hashed."""
        try:
            prepared = block.get_prep_value(value)
            serialized = json.dumps(prepared, sort_keys=True, default=str)
        except Exception:
            return None
        return segment_hash(serialized)

    def collect_nontext_values(self, page: object) -> dict[str, Any]:
        """Map each non-text StreamField leaf to its current value."""
        values: dict[str, Any] = {}

        def handle_value(key, block, value):
            values[key] = value
            return value

        for field_name in self._field_names(page):
            self._walk_value(
                getattr(page, field_name, None),
                lambda key, text: text,
                field_name,
                handle_value,
                mutate=False,
            )
        return values

    def collect_nontext_hashes(self, page: object) -> dict[str, str]:
        """Map each non-text StreamField leaf to a hash of its current value."""
        hashes: dict[str, str] = {}

        def handle_value(key, block, value):
            value_hash = self._hash_block_value(block, value)
            if value_hash is not None:
                hashes[key] = value_hash
            return value

        for field_name in self._field_names(page):
            self._walk_value(
                getattr(page, field_name, None),
                lambda key, text: text,
                field_name,
                handle_value,
                mutate=False,
            )
        return hashes

    def _resolve_nontext(
        self, key, block, source_value, target_values, nontext_memory, updates
    ):
        """Decide the value to write for one non-text leaf (sticky override)."""
        source_hash = self._hash_block_value(block, source_value)
        if source_hash is None:
            # Can't hash this block — fall back to following the source (the
            # previous behaviour), without tracking it.
            return source_value

        target_value = target_values.get(key, _MISSING)
        known = nontext_memory.get(key)
        if target_value is _MISSING or known is None:
            # New block, or first time we track it: sync from source.
            updates[key] = (source_hash, source_hash)
            return source_value

        written_hash = known[1]
        if self._hash_block_value(block, target_value) == written_hash:
            # The target still holds what we wrote — not overridden — so follow
            # the source.
            updates[key] = (source_hash, source_hash)
            return source_value

        # The translator overrode this block: keep their value, and preserve the
        # written hash so it stays recognised as an override next time.
        updates[key] = (source_hash, written_hash)
        return target_value

    def apply_resolved_segments(
        self,
        source_page: object,
        target_page: object,
        resolved: dict[str, str],
        nontext_memory: dict | None = None,
        replaced_edits: list[dict] | None = None,
    ) -> PageTranslationResult:
        """Rebuild target_page's fields from source_page, substituting per key.

        ``resolved`` maps every text segment key to the text to write — a fresh
        translation for changed blocks, or the preserved (possibly hand-edited)
        target text for unchanged ones. Non-text leaves follow the source unless
        the translator overrode them (sticky), using ``nontext_memory``. The
        result is saved as a draft revision.
        """
        result = PageTranslationResult(replaced_edits=list(replaced_edits or []))
        nontext_memory = nontext_memory or {}
        target_nontext = self.collect_nontext_values(target_page)

        setattr(target_page, "_heimdallur_translation_in_progress", True)
        try:
            for field_name in self._field_names(source_page):
                counted = [0]

                def handle(key, text, counted=counted):
                    if key in resolved:
                        counted[0] += 1
                        return resolved[key]
                    return text

                def handle_value(key, block, value):
                    result.nontext_keys.add(key)
                    return self._resolve_nontext(
                        key,
                        block,
                        value,
                        target_nontext,
                        nontext_memory,
                        result.nontext_updates,
                    )

                new_value = self._walk_value(
                    getattr(source_page, field_name, None),
                    handle,
                    field_name,
                    handle_value,
                )
                setattr(target_page, field_name, new_value)
                if counted[0]:
                    result.translated_fields.append(field_name)

            self._apply_child_segments(target_page, resolved, result)
            _save_draft(target_page)
        finally:
            setattr(target_page, "_heimdallur_translation_in_progress", False)

        setattr(target_page, "_heimdallur_skipped_translation_fields", [])
        return result

    def _walk_value(
        self, value: Any, handle, path: str, handle_value=None, mutate: bool = True
    ) -> Any:
        """Path-aware walk over a single field value (used by the keyed methods).

        ``handle(key, text)`` returns the replacement text for each text leaf;
        ``handle_value(key, block, value)`` (optional) intercepts non-text leaves
        inside StreamFields. ``mutate=False`` performs a read-only walk (used by
        the collect methods) that never writes back into the source — important
        because writing into a StreamField list regenerates its item ids.
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
                self._walk_value(item, handle, f"{path}.{index}", handle_value, mutate)
                for index, item in enumerate(value)
            ]

        if isinstance(value, tuple):
            return tuple(
                self._walk_value(item, handle, f"{path}.{index}", handle_value, mutate)
                for index, item in enumerate(value)
            )

        if isinstance(value, dict):
            out = {}
            for key, item in value.items():
                if key in _NON_TRANSLATABLE_BLOCK_KEYS:
                    out[key] = item
                else:
                    out[key] = self._walk_value(
                        item, handle, f"{path}.{key}", handle_value, mutate
                    )
            return out

        if _is_stream_value_like(value):
            if _is_real_stream_value(value):
                return self._walk_stream_value(
                    value, handle, path, handle_value, mutate
                )
            translated_raw = self._walk_value(
                list(value.raw_data), handle, path, handle_value, mutate
            )
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
