"""Tests for page-level translation."""

from dataclasses import dataclass

from django.test import override_settings
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from wagtail_heimdallur.engines.page_translation import PageTranslationEngine
from wagtail_heimdallur.exceptions import BackendError


class Locale:
    def __init__(self, language_code):
        self.language_code = language_code


class RichText:
    def __init__(self, source):
        self.source = source

    def __eq__(self, other):
        return isinstance(other, RichText) and other.source == self.source


@dataclass
class Page:
    title: str
    body: RichText
    stream: list
    locale: Locale
    saved_revision: bool = False

    def get_translatable_field_names(self):
        return ["title", "body", "stream"]

    def save_revision(self):
        self.saved_revision = True


class RecordingTranslationEngine:
    def __init__(self, failures=None):
        self.failures = set(failures or [])
        self.calls = []

    def translate(self, text, source_language, target_language):
        self.calls.append((text, source_language, target_language))
        if text in self.failures:
            raise BackendError(f"cannot translate {text}")
        return f"{text}[{source_language}->{target_language}]"


text_values = st.text(
    alphabet=st.characters(blacklist_categories=["Cs"]),
    min_size=1,
    max_size=20,
)


@given(
    title=text_values,
    body=text_values,
    stream_text=text_values,
    nested_text=text_values,
)
@settings(max_examples=50)
def test_page_translation_processes_translatable_field_types(
    title,
    body,
    stream_text,
    nested_text,
):
    """Property 12: text, rich text, and StreamField-like values are translated."""
    source = Page(
        title=title,
        body=RichText(body),
        stream=[
            {"type": "paragraph", "value": stream_text},
            {"type": "struct", "value": {"heading": nested_text}},
        ],
        locale=Locale("is"),
    )
    target = Page(
        title=title,
        body=RichText(body),
        stream=source.stream,
        locale=Locale("en"),
    )
    translation_engine = RecordingTranslationEngine()

    result = PageTranslationEngine(translation_engine).translate_page(source, target)

    assert target.title == f"{title}[is->en]"
    assert target.body == RichText(f"{body}[is->en]")
    assert target.stream == [
        {
            "type": "paragraph",
            "value": f"{stream_text}[is->en]",
        },
        {
            "type": "struct",
            "value": {"heading": f"{nested_text}[is->en]"},
        },
    ]
    assert result.translated_fields == ["title", "body", "stream"]
    assert result.skipped_fields == []
    assert target.saved_revision is True


@given(
    title=text_values,
    body=text_values,
    stream_text=text_values,
)
@settings(max_examples=50)
def test_partial_field_failure_does_not_prevent_remaining_translations(
    title,
    body,
    stream_text,
):
    """Property 13: failed fields are skipped while remaining fields translate."""
    source = Page(
        title=title,
        body=RichText(body),
        stream=[{"type": "paragraph", "value": stream_text}],
        locale=Locale("is"),
    )
    target = Page(
        title=title,
        body=RichText(body),
        stream=source.stream,
        locale=Locale("en"),
    )
    translation_engine = RecordingTranslationEngine(failures={body})
    assume(title != body)
    assume(stream_text != body)

    result = PageTranslationEngine(translation_engine).translate_page(source, target)

    assert target.title == f"{title}[is->en]"
    assert target.body == RichText(body)
    assert target.stream == [
        {
            "type": "paragraph",
            "value": f"{stream_text}[is->en]",
        }
    ]
    assert "title" in result.translated_fields
    assert "stream" in result.translated_fields
    assert [skipped.field_name for skipped in result.skipped_fields] == ["body"]
    assert target._heimdallur_skipped_translation_fields == ["body"]
    assert target.saved_revision is True


def test_page_translation_collects_texts_in_field_order():
    source = Page(
        title="Titill",
        body=RichText("Meginmál"),
        stream=[{"type": "paragraph", "value": "Straumur"}],
        locale=Locale("is"),
    )

    texts = PageTranslationEngine().collect_texts(source)

    assert texts == ["Titill", "Meginmál", "Straumur"]


@dataclass
class StreamPage:
    stream: object
    locale: Locale
    saved_revision: bool = False

    def get_translatable_field_names(self):
        return ["stream"]

    def save_revision(self):
        self.saved_revision = True


def _real_stream_page(language_code):
    """A page whose only field is a real Wagtail StreamField value mixing text
    blocks, a nested StructBlock, a ListBlock and a non-text block."""
    from wagtail import blocks

    class _Stream(blocks.StreamBlock):
        heading = blocks.CharBlock()
        body = blocks.RichTextBlock()
        section = blocks.StructBlock(
            [("title", blocks.CharBlock()), ("intro", blocks.RichTextBlock())]
        )
        bullets = blocks.ListBlock(blocks.CharBlock())
        number = blocks.IntegerBlock()

    raw = [
        {"type": "heading", "value": "Fyrirsogn", "id": "a"},
        {"type": "body", "value": "<p>Texti</p>", "id": "b"},
        {
            "type": "section",
            "value": {"title": "Titill", "intro": "<p>Inn</p>"},
            "id": "c",
        },
        {
            "type": "bullets",
            "value": [
                {"type": "item", "value": "Eitt", "id": "d1"},
                {"type": "item", "value": "Tvo", "id": "d2"},
            ],
            "id": "d",
        },
        {"type": "number", "value": 7, "id": "e"},
    ]
    return StreamPage(stream=_Stream().to_python(raw), locale=Locale(language_code))


def test_real_streamfield_collects_only_text_blocks():
    """Block-aware traversal collects text blocks (incl. nested) and skips the
    rest — block UUIDs and non-text blocks are not translated."""
    texts = PageTranslationEngine().collect_texts(_real_stream_page("is"))

    assert len(texts) == 6
    assert texts[0] == "Fyrirsogn"  # CharBlock
    assert texts[2] == "Titill"  # nested StructBlock CharBlock
    assert texts[4:6] == ["Eitt", "Tvo"]  # ListBlock items
    assert "Texti" in texts[1] and "Inn" in texts[3]  # RichTextBlocks
    assert "7" not in "".join(texts)  # IntegerBlock skipped


def test_real_streamfield_apply_preserves_structure_and_non_text():
    engine = PageTranslationEngine()
    texts = engine.collect_texts(_real_stream_page("is"))
    translated = [f"{text}-EN" for text in texts]
    target = _real_stream_page("en")

    result = engine.apply_translated_texts(
        _real_stream_page("is"), target, translated
    )

    out = list(target.stream)
    assert out[0].value == "Fyrirsogn-EN"
    assert out[1].value.source == "<p>Texti</p>-EN"
    assert out[2].value["title"] == "Titill-EN"
    assert out[2].value["intro"].source == "<p>Inn</p>-EN"
    assert list(out[3].value) == ["Eitt-EN", "Tvo-EN"]
    assert out[4].value == 7  # IntegerBlock unchanged
    assert "stream" in result.translated_fields


def test_real_streamfield_collect_segments_uses_stable_block_id_keys():
    """Segment keys are derived from the field name plus the path of block ids,
    so they survive edits/reordering rather than depending on position."""
    segments = dict(PageTranslationEngine().collect_segments(_real_stream_page("is")))

    assert segments["stream:a"] == "Fyrirsogn"  # CharBlock
    assert segments["stream:b"] == "<p>Texti</p>"  # RichTextBlock
    assert segments["stream:c:title"] == "Titill"  # nested StructBlock child
    assert segments["stream:c:intro"] == "<p>Inn</p>"
    assert segments["stream:d:d1"] == "Eitt"  # ListBlock items, keyed by item id
    assert segments["stream:d:d2"] == "Tvo"
    assert all("number" not in key for key in segments)  # IntegerBlock skipped


def test_real_streamfield_apply_resolved_segments_is_per_block():
    """apply_resolved_segments substitutes only the keys it is given and rebuilds
    the rest of the structure from the source."""
    engine = PageTranslationEngine()
    target = _real_stream_page("en")

    result = engine.apply_resolved_segments(
        _real_stream_page("is"),
        target,
        {"stream:a": "NEW HEADING", "stream:d:d2": "NEW BULLET"},
    )

    out = list(target.stream)
    assert out[0].value == "NEW HEADING"  # resolved
    assert list(out[3].value) == ["Eitt", "NEW BULLET"]  # one bullet resolved
    assert out[2].value["title"] == "Titill"  # untouched key keeps source text
    assert out[4].value == 7  # IntegerBlock preserved
    assert "stream" in result.translated_fields


def _number_block(page):
    for child in page.stream:
        if type(child.block).__name__ == "IntegerBlock":
            return child.block
    raise AssertionError("no IntegerBlock in fixture")


def _set_number(page, value):
    for child in page.stream:
        if type(child.block).__name__ == "IntegerBlock":
            child.value = value


def _get_number(page):
    for child in page.stream:
        if type(child.block).__name__ == "IntegerBlock":
            return child.value
    return None


def test_collect_nontext_hashes_covers_only_non_text_leaves():
    hashes = PageTranslationEngine().collect_nontext_hashes(_real_stream_page("is"))
    assert "stream:e" in hashes  # IntegerBlock (non-text)
    assert "stream:a" not in hashes  # heading CharBlock is a text leaf


def test_resolve_nontext_sticky_decisions():
    engine = PageTranslationEngine()
    block = _number_block(_real_stream_page("is"))
    seven = engine._hash_block_value(block, 7)

    # New block (no target / no memory): sync from source and record it.
    updates = {}
    assert engine._resolve_nontext("k", block, 7, {"k": 7}, {}, updates) == 7
    assert updates["k"] == (seven, seven)

    # Target still holds what we wrote (not overridden): follow the source change.
    updates = {}
    assert engine._resolve_nontext("k", block, 8, {"k": 7}, {"k": (seven, seven)}, updates) == 8

    # Target diverged (overridden): keep it, even though the source changed.
    updates = {}
    assert engine._resolve_nontext("k", block, 8, {"k": 99}, {"k": (seven, seven)}, updates) == 99


def test_apply_keeps_overridden_nontext_block():
    engine = PageTranslationEngine()
    source = _real_stream_page("is")  # number = 7
    target = _real_stream_page("en")
    _set_number(target, 99)  # translator's per-locale override
    seven = engine._hash_block_value(_number_block(source), 7)

    engine.apply_resolved_segments(
        source, target, {}, nontext_memory={"stream:e": (seven, seven)}
    )

    assert _get_number(target) == 99  # sticky override survived the rebuild


def test_apply_syncs_nontext_block_when_not_overridden():
    engine = PageTranslationEngine()
    source = _real_stream_page("is")
    _set_number(source, 8)  # source value changed
    target = _real_stream_page("en")  # still holds 7 (what we last wrote)
    seven = engine._hash_block_value(_number_block(source), 7)

    engine.apply_resolved_segments(
        source, target, {}, nontext_memory={"stream:e": (seven, seven)}
    )

    assert _get_number(target) == 8  # un-overridden block follows the source


def _optout_page():
    from wagtail import blocks

    class _NoTranslate(blocks.CharBlock):
        translatable = False

    class _Stream(blocks.StreamBlock):
        heading = blocks.CharBlock()
        raw = blocks.RawHTMLBlock()
        code = _NoTranslate()

    raw = [
        {"type": "heading", "value": "Hi", "id": "a"},
        {"type": "raw", "value": "<script>x()</script>", "id": "b"},
        {"type": "code", "value": "verbatim", "id": "c"},
    ]
    return StreamPage(stream=_Stream().to_python(raw), locale=Locale("is"))


def test_untranslatable_blocks_are_skipped_for_translation():
    engine = PageTranslationEngine()
    page = _optout_page()

    # Only the plain CharBlock is collected for translation.
    assert dict(engine.collect_segments(page)) == {"stream:a": "Hi"}
    # RawHTMLBlock (excluded by default) and translatable=False block are tracked
    # as non-text instead (synced from source / overridable).
    nontext = engine.collect_nontext_hashes(page)
    assert "stream:b" in nontext and "stream:c" in nontext


@override_settings(
    WAGTAIL_HEIMDALLUR={"PAGE_TRANSLATION": {"untranslatable_blocks": []}}
)
def test_raw_html_translated_when_not_excluded():
    engine = PageTranslationEngine()
    segments = dict(engine.collect_segments(_optout_page()))
    assert segments["stream:b"] == "<script>x()</script>"  # now translated


class _FakeChild:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class _FakeRelManager:
    def __init__(self, items):
        self._items = list(items)
        self.set_calls = []

    def all(self):
        return list(self._items)

    def set(self, items, bulk=True):
        self._items = list(items)
        self.set_calls.append(bulk)


class _FakeFormPage:
    def __init__(self, fields=None, page_fields=None):
        self.form_fields = _FakeRelManager(fields or [])
        self._page_fields = page_fields or {}
        for key, value in self._page_fields.items():
            setattr(self, key, value)
        self.saved = False

    def get_translatable_field_names(self):
        return list(self._page_fields)

    def save_revision(self):
        self.saved = True


def test_child_relation_skipped_when_not_translatable():
    # Children without a translation_key can't be matched reliably, so the whole
    # relation is skipped (only the page field is collected).
    page = _FakeFormPage(
        fields=[_FakeChild(label="Nafn", help_text="", choices="")],
        page_fields={"title": "Titill"},
    )

    segments = dict(PageTranslationEngine().collect_segments(page))

    assert segments == {"title": "Titill"}


def test_child_segments_collected_and_applied_by_translation_key():
    source = _FakeFormPage(
        fields=[
            _FakeChild(label="Nafn", help_text="Hjálp", choices="", translation_key="tk-1"),
        ],
        page_fields={"title": "Titill"},
    )
    target = _FakeFormPage(
        fields=[_FakeChild(label="Nafn", help_text="Hjálp", choices="", translation_key="tk-1")],
        page_fields={"title": "Titill"},
    )

    segments = dict(PageTranslationEngine().collect_segments(source))
    assert segments["form_fields:tk-1:label"] == "Nafn"  # keyed by translation_key
    assert segments["form_fields:tk-1:help_text"] == "Hjálp"

    PageTranslationEngine().apply_resolved_segments(
        source, target, {"form_fields:tk-1:label": "Name"}
    )
    assert target.form_fields.all()[0].label == "Name"
    assert target.form_fields.set_calls  # persisted via .set()


def test_apply_matches_translatable_children_regardless_of_order():
    # Target children are in a different order than the source; matching by
    # translation_key must still put each translation on the right child.
    target = _FakeFormPage(
        fields=[
            _FakeChild(label="B", help_text="", choices="", translation_key="tk-b"),
            _FakeChild(label="A", help_text="", choices="", translation_key="tk-a"),
        ]
    )

    PageTranslationEngine().apply_resolved_segments(
        _FakeFormPage(),
        target,
        {"form_fields:tk-a:label": "A-EN", "form_fields:tk-b:label": "B-EN"},
    )

    labels = {c.translation_key: c.label for c in target.form_fields.all()}
    assert labels["tk-a"] == "A-EN"
    assert labels["tk-b"] == "B-EN"


def test_untranslatable_page_fields_are_excluded():
    page = _FakeFormPage(
        page_fields={
            "title": "Titill",
            "to_address": "forms@example.is",
            "from_address": "no-reply@example.is",
        }
    )

    segments = dict(PageTranslationEngine().collect_segments(page))

    assert "title" in segments
    assert "to_address" not in segments  # email config not translated
    assert "from_address" not in segments


def test_list_block_round_trips_without_collect_corrupting_ids():
    """A full collect->apply round-trip must translate ListBlock items.

    The read-only collect walk must not write back into the source: writing into
    a Wagtail ListValue mints fresh item ids, which would change the keys between
    the collect pass (that builds the translations) and the apply pass (that
    looks them up), silently leaving list content untranslated.
    """
    from wagtail import blocks

    class _Stream(blocks.StreamBlock):
        bullets = blocks.ListBlock(blocks.CharBlock())

    # Old-format list value (plain strings, no per-item ids).
    raw = [{"type": "bullets", "id": "b", "value": ["Eitt", "Tvo"]}]
    source = StreamPage(stream=_Stream().to_python(raw), locale=Locale("is"))
    target = StreamPage(stream=_Stream().to_python(raw), locale=Locale("en"))

    engine = PageTranslationEngine()
    # Build the resolved map from the keys collect actually produces, then apply.
    resolved = {
        key: f"{text}-EN" for key, text in engine.collect_segments(source)
    }
    engine.apply_resolved_segments(source, target, resolved)

    assert list(list(target.stream)[0].value) == ["Eitt-EN", "Tvo-EN"]


def test_collect_segments_does_not_mutate_source_list_ids():
    source = _real_stream_page("is")
    bullets = next(
        c for c in source.stream if type(c.block).__name__ == "ListBlock"
    )
    before = [bb.id for bb in bullets.value.bound_blocks]

    PageTranslationEngine().collect_segments(source)

    after = [bb.id for bb in bullets.value.bound_blocks]
    assert before == after  # read-only collect leaves the stable ids untouched


def test_page_translation_applies_translated_texts_in_field_order():
    source = Page(
        title="Titill",
        body=RichText("Meginmál"),
        stream=[{"type": "paragraph", "value": "Straumur"}],
        locale=Locale("is"),
    )
    target = Page(
        title="Titill",
        body=RichText("Meginmál"),
        stream=source.stream,
        locale=Locale("en"),
    )

    result = PageTranslationEngine().apply_translated_texts(
        source,
        target,
        ["Title", "Body", "Stream"],
    )

    assert target.title == "Title"
    assert target.body == RichText("Body")
    assert target.stream == [{"type": "paragraph", "value": "Stream"}]
    assert result.translated_fields == ["title", "body", "stream"]
    assert target.saved_revision is True
