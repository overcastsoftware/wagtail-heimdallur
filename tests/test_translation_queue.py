"""Tests for queued page translation jobs."""

from django.core.management import call_command
from wagtail.models import Page
import pytest

from wagtail_heimdallur.engines.page_translation import (
    PageTranslationEngine,
    queue_copied_page_translation,
)
from wagtail_heimdallur.engines.translation_queue import TranslationQueueProcessor
from wagtail_heimdallur.exceptions import BackendError
from wagtail_heimdallur.models import TranslationJob


class SuffixTranslationEngine:
    def translate(self, text, source_language, target_language):
        return f"{text}[{source_language}->{target_language}]"


class FailingTranslationEngine:
    def translate(self, text, source_language, target_language):
        raise BackendError("translation backend unavailable")


@pytest.mark.django_db
def test_queue_copied_page_translation_persists_job():
    source, target = _create_source_and_target_pages("queue")

    job = queue_copied_page_translation(source, target)

    assert job.status == TranslationJob.Status.QUEUED
    assert job.source_page == source
    assert job.target_page == target
    assert job.source_language == _language_code(source)
    assert job.target_language == _language_code(target)


@pytest.mark.django_db
def test_translation_queue_processor_translates_queued_page():
    source, target = _create_source_and_target_pages("process")
    job = TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
    )
    processor = TranslationQueueProcessor(
        PageTranslationEngine(SuffixTranslationEngine()),
    )

    processed_count = processor.process_queued()

    assert processed_count == 1
    job.refresh_from_db()
    target.refresh_from_db()
    assert job.status == TranslationJob.Status.COMPLETED
    assert job.attempts == 1
    assert "title" in job.translated_fields
    assert job.error_message == ""
    assert target.get_latest_revision().content["title"] == "Source process[is->en]"


@pytest.mark.django_db
def test_translation_queue_processor_records_failures():
    source, target = _create_source_and_target_pages("failure")
    job = TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
    )
    processor = TranslationQueueProcessor(
        PageTranslationEngine(FailingTranslationEngine()),
    )

    processor.process_job(job)

    job.refresh_from_db()
    assert job.status == TranslationJob.Status.COMPLETED_WITH_WARNINGS
    assert job.attempts == 1
    assert job.skipped_fields
    assert job.error_message == ""


@pytest.mark.django_db
def test_process_translation_queue_command_reports_processed_count(capsys):
    source, target = _create_source_and_target_pages("command")
    TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
    )

    call_command("process_heimdallur_translation_queue", limit=0)

    output = capsys.readouterr().out
    assert "Processed 0 of 1 queued translation jobs." in output
    assert "1 queued translation jobs remain." in output


def _create_source_and_target_pages(slug_suffix):
    root = Page.get_first_root_node()
    source = Page(title=f"Source {slug_suffix}", slug=f"source-{slug_suffix}")
    target = Page(title=f"Target {slug_suffix}", slug=f"target-{slug_suffix}")
    root.add_child(instance=source)
    root.add_child(instance=target)
    return source, target


def _language_code(page):
    locale = getattr(page, "locale", None)
    if locale is None:
        return ""
    return locale.language_code
