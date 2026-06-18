"""Tests for queued page translation jobs."""

from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from wagtail.models import Page
import pytest
from datetime import timedelta

from wagtail_heimdallur.backends.base import TextTranslationStatus
from wagtail_heimdallur.engines.page_translation import (
    PageTranslationEngine,
    queue_copied_page_translation,
)
from wagtail_heimdallur.engines.translation_queue import TranslationQueueProcessor
from wagtail_heimdallur.exceptions import BackendError
from wagtail_heimdallur.models import TranslationJob


class SuffixTranslationEngine:
    def __init__(self):
        self.started_texts = []

    def translate(self, text, source_language, target_language):
        return f"{text}[{source_language}->{target_language}]"

    def start_text_translation(self, text, source_language, target_language):
        self.started_texts.append(text)
        return f"remote-task-{len(self.started_texts)}"

    def get_text_translation_status(self, task_id, source_language, target_language):
        index = int(task_id.rsplit("-", 1)[1]) - 1
        return TextTranslationStatus(
            task_id=task_id,
            status="completed",
            progress=100,
            text=f"{self.started_texts[index]}[{source_language}->{target_language}]",
        )


class FailingTranslationEngine:
    def translate(self, text, source_language, target_language):
        raise BackendError("translation backend unavailable")

    def start_text_translation(self, text, source_language, target_language):
        raise BackendError("translation backend unavailable")


class InProgressTranslationEngine:
    def get_text_translation_status(self, task_id, source_language, target_language):
        return TextTranslationStatus(
            task_id=task_id,
            status="in_progress",
            progress=40,
        )


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
def test_translation_queue_processor_submits_queued_page_translation():
    source, target = _create_source_and_target_pages("process")
    job = TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
    )
    translation_engine = SuffixTranslationEngine()
    processor = TranslationQueueProcessor(PageTranslationEngine(translation_engine))

    processed_count = processor.process_queued()

    assert processed_count == 1
    job.refresh_from_db()
    target.refresh_from_db()
    assert job.status == TranslationJob.Status.RUNNING
    assert job.remote_task_id == "remote-task-1"
    assert len(job.remote_tasks) >= 1
    assert job.attempts == 1
    assert translation_engine.started_texts[0] == "Source process"
    assert target.get_latest_revision() is None


@pytest.mark.django_db
def test_translation_queue_processor_applies_completed_remote_translation():
    source, target = _create_source_and_target_pages("complete")
    job = TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
        status=TranslationJob.Status.RUNNING,
        attempts=1,
        remote_task_id="remote-task-1",
    )
    translation_engine = SuffixTranslationEngine()
    translation_engine.started_texts = PageTranslationEngine().collect_texts(source)
    job.remote_tasks = [
        {
            "index": index,
            "task_id": f"remote-task-{index + 1}",
            "status": "in_progress",
        }
        for index, _text in enumerate(translation_engine.started_texts)
    ]
    job.save(update_fields=["remote_tasks"])
    processor = TranslationQueueProcessor(PageTranslationEngine(translation_engine))

    processed_count = processor.process_queued()

    assert processed_count == 1
    job.refresh_from_db()
    target.refresh_from_db()
    assert job.status == TranslationJob.Status.COMPLETED
    assert job.attempts == 1
    assert "title" in job.translated_fields
    assert job.error_message == ""
    assert target.get_latest_revision().content["title"] == "Source complete[is->en]"


@pytest.mark.django_db
def test_translation_queue_processor_leaves_in_progress_jobs_running():
    source, target = _create_source_and_target_pages("in-progress")
    job = TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
        status=TranslationJob.Status.RUNNING,
        attempts=1,
        remote_task_id="remote-task-1",
        remote_tasks=[
            {
                "index": 0,
                "task_id": "remote-task-1",
                "status": "in_progress",
            }
        ],
    )
    processor = TranslationQueueProcessor(
        PageTranslationEngine(InProgressTranslationEngine()),
    )

    processed_count = processor.process_queued()

    assert processed_count == 1
    job.refresh_from_db()
    assert job.status == TranslationJob.Status.RUNNING
    assert job.error_message == ""
    assert job.remote_progress_label == "0/1 completed (40%)"


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
    assert job.status == TranslationJob.Status.FAILED
    assert job.attempts == 1
    assert job.skipped_fields == []
    assert "translation backend unavailable" in job.error_message


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
    assert "Processed 0 of 1 translation jobs." in output
    assert "1 translation jobs remain." in output


@pytest.mark.django_db
def test_process_translation_queue_command_can_requeue_warning_jobs(capsys):
    source, target = _create_source_and_target_pages("retry-warning")
    job = TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
        status=TranslationJob.Status.COMPLETED_WITH_WARNINGS,
        translated_fields=[],
        skipped_fields=[
            {
                "field_name": "title",
                "error": "Miðeind rejected the request.",
            }
        ],
    )

    call_command(
        "process_heimdallur_translation_queue",
        retry_warnings=True,
        limit=0,
    )

    job.refresh_from_db()
    output = capsys.readouterr().out
    assert "Requeued 1 translation jobs." in output
    assert job.status == TranslationJob.Status.QUEUED
    assert job.skipped_fields == []


@pytest.mark.django_db
def test_process_translation_queue_command_can_requeue_stale_running_jobs(capsys):
    source, target = _create_source_and_target_pages("retry-running")
    job = TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
        status=TranslationJob.Status.RUNNING,
        remote_task_id="remote-task-1",
        remote_tasks=[
            {
                "index": 0,
                "task_id": "remote-task-1",
                "status": "in_progress",
            }
        ],
    )
    TranslationJob.objects.filter(pk=job.pk).update(
        updated_at=timezone.now() - timedelta(minutes=90),
    )

    call_command(
        "process_heimdallur_translation_queue",
        retry_running=True,
        older_than_minutes=60,
        limit=0,
    )

    job.refresh_from_db()
    output = capsys.readouterr().out
    assert "Requeued 1 stale running translation jobs." in output
    assert job.status == TranslationJob.Status.QUEUED
    assert job.remote_task_id == ""
    assert job.remote_tasks == []


@pytest.mark.django_db
def test_retry_running_requires_age_guard():
    with pytest.raises(CommandError):
        call_command("process_heimdallur_translation_queue", retry_running=True)


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
