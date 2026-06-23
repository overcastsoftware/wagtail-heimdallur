"""Tests for page-level translation."""

from dataclasses import dataclass

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
