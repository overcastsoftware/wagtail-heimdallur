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
