"""Tests for queued page translation jobs."""

from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from wagtail.models import Locale, Page
import pytest
from datetime import timedelta

from wagtail_heimdallur.backends.base import TextTranslationStatus
from wagtail_heimdallur.engines.page_translation import (
    PageTranslationEngine,
    enqueue_translation_updates,
    page_has_translation_targets,
    queue_copied_page_translation,
    queue_update_translation,
    segment_hash,
)
from wagtail_heimdallur.engines.translation_queue import TranslationQueueProcessor
from wagtail_heimdallur.exceptions import BackendError
from wagtail_heimdallur.models import TranslationJob, TranslationSegment


def _in_progress_tasks(page):
    """Build per-segment remote tasks (keyed) as the submit phase would."""
    segments = PageTranslationEngine().collect_segments(page)
    tasks = [
        {
            "index": index,
            "key": key,
            "task_id": f"remote-task-{index + 1}",
            "status": "in_progress",
            "source_hash": segment_hash(text),
        }
        for index, (key, text) in enumerate(segments)
    ]
    return segments, tasks


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


class PartialFailTranslationEngine:
    """Completes every segment except one, which fails on its own."""

    def __init__(self, fail_index, error="SameLanguageError"):
        self.started_texts = []
        self.fail_index = fail_index
        self.error = error

    def start_text_translation(self, text, source_language, target_language):
        self.started_texts.append(text)
        return f"remote-task-{len(self.started_texts)}"

    def get_text_translation_status(self, task_id, source_language, target_language):
        index = int(task_id.rsplit("-", 1)[1]) - 1
        if index == self.fail_index:
            return TextTranslationStatus(
                task_id=task_id, status="failed", progress=100, error=self.error
            )
        return TextTranslationStatus(
            task_id=task_id,
            status="completed",
            progress=100,
            text=f"{self.started_texts[index]}[{source_language}->{target_language}]",
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
    segments, job.remote_tasks = _in_progress_tasks(source)
    translation_engine.started_texts = [text for _key, text in segments]
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
def test_per_segment_failure_skips_segment_and_completes_with_warnings():
    source, target = _create_source_and_target_pages("partial")
    segments, remote_tasks = _in_progress_tasks(source)
    fail_index = len(segments) - 1  # the last segment "fails" (e.g. same language)
    engine = PartialFailTranslationEngine(fail_index)
    engine.started_texts = [text for _key, text in segments]
    job = TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
        status=TranslationJob.Status.RUNNING,
        attempts=1,
        remote_tasks=remote_tasks,
    )
    processor = TranslationQueueProcessor(PageTranslationEngine(engine))

    processor.process_job(job)

    job.refresh_from_db()
    target.refresh_from_db()
    # The whole job is NOT failed; it completes with the bad segment skipped.
    assert job.status == TranslationJob.Status.COMPLETED_WITH_WARNINGS
    assert len(job.skipped_fields) == 1
    assert "SameLanguageError" in job.skipped_fields[0]["error"]
    # The other segments were still translated.
    assert target.get_latest_revision().content["title"] == "Source partial[is->en]"


def _seed_memory(target, segments, *, translation_hashes=None):
    """Record translation memory marking every segment as already translated."""
    translation_hashes = translation_hashes or {}
    for key, text in segments:
        TranslationSegment.objects.create(
            target_page=target,
            segment_key=key,
            source_hash=segment_hash(text),
            translation_hash=translation_hashes.get(key, segment_hash(f"machine::{text}")),
        )


@pytest.mark.django_db
def test_incremental_unchanged_source_is_a_noop():
    source, target = _create_source_and_target_pages("noop")
    segments = PageTranslationEngine().collect_segments(source)
    _seed_memory(target, segments)
    job = TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
    )
    engine = SuffixTranslationEngine()
    processor = TranslationQueueProcessor(PageTranslationEngine(engine))

    processor.process_job(job)

    job.refresh_from_db()
    target.refresh_from_db()
    # Nothing changed, so no API calls and no new draft were produced.
    assert job.status == TranslationJob.Status.COMPLETED
    assert engine.started_texts == []
    assert job.remote_tasks == []
    assert target.get_latest_revision() is None


@pytest.mark.django_db
def test_incremental_submits_only_changed_segment():
    source, target = _create_source_and_target_pages("changed")
    segments = PageTranslationEngine().collect_segments(source)
    _seed_memory(target, segments)
    # The title's source text changes; everything else stays the same.
    source.title = "A brand new title"
    source.save()
    job = TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
    )
    engine = SuffixTranslationEngine()
    processor = TranslationQueueProcessor(PageTranslationEngine(engine))

    processor.process_job(job)

    job.refresh_from_db()
    # Only the changed segment was submitted for translation.
    assert engine.started_texts == ["A brand new title"]
    assert len(job.remote_tasks) == 1
    assert job.remote_tasks[0]["key"] == "title"


@pytest.mark.django_db
def test_incremental_preserves_hand_edited_unchanged_block():
    source, target = _create_source_and_target_pages("preserve")
    # A human corrected the slug on the translated page.
    target.slug = "human-edited-slug"
    target.save()

    # Only the title is queued for (re)translation; every other segment is
    # treated as unchanged (no remote task), so it must be preserved as-is.
    job = TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
        status=TranslationJob.Status.RUNNING,
        attempts=1,
        remote_tasks=[
            {
                "index": 0,
                "key": "title",
                "task_id": "remote-task-1",
                "status": "in_progress",
                "source_hash": segment_hash(source.title),
            }
        ],
    )
    engine = SuffixTranslationEngine()
    engine.started_texts = [source.title]
    processor = TranslationQueueProcessor(PageTranslationEngine(engine))

    processor.process_job(job)

    job.refresh_from_db()
    target.refresh_from_db()
    content = target.get_latest_revision().content
    assert job.status == TranslationJob.Status.COMPLETED
    assert content["title"] == f"{source.title}[is->en]"  # re-translated
    assert content["slug"] == "human-edited-slug"  # human edit preserved


@pytest.mark.django_db
def test_incremental_preserves_existing_translation_not_live_source_text():
    root = Page.get_first_root_node()
    source = Page(title="Hús", slug="hus-src", seo_title="Hús SEO")
    root.add_child(instance=source)
    # The translated page's LIVE row is still the Icelandic copy...
    target = Page(title="Hús", slug="hus-tgt", seo_title="Hús SEO")
    root.add_child(instance=target)
    # ...while its latest draft revision holds the existing English translation.
    target.title = "House"
    target.seo_title = "House SEO"
    target.save_revision()

    # Only seo_title is (re)translated; title is unchanged and must keep the
    # existing English translation rather than reverting to the source text.
    job = TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
        status=TranslationJob.Status.RUNNING,
        attempts=1,
        remote_tasks=[
            {
                "index": 0,
                "key": "seo_title",
                "task_id": "remote-task-1",
                "status": "in_progress",
                "source_hash": segment_hash("Hús SEO"),
            }
        ],
    )
    engine = SuffixTranslationEngine()
    engine.started_texts = ["Hús SEO"]
    processor = TranslationQueueProcessor(PageTranslationEngine(engine))

    processor.process_job(job)

    target.refresh_from_db()
    content = target.get_latest_revision().content
    assert content["title"] == "House"  # existing translation preserved
    assert content["seo_title"] == "Hús SEO[is->en]"  # changed block re-translated


@pytest.mark.django_db
def test_incremental_flags_replaced_edit():
    source, target = _create_source_and_target_pages("replaced")
    # The translated title was hand-edited away from the machine output...
    target.title = "Human polished title"
    target.save()
    # ...and the source title has since changed (memory records the old source
    # and the original machine translation).
    TranslationSegment.objects.create(
        target_page=target,
        segment_key="title",
        source_hash=segment_hash("the previous source title"),
        translation_hash=segment_hash("the original machine title"),
    )
    job = TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
    )
    engine = SuffixTranslationEngine()
    processor = TranslationQueueProcessor(PageTranslationEngine(engine))

    processor.process_job(job)

    job.refresh_from_db()
    titles = [edit for edit in job.replaced_edits if edit["previous"] == "Human polished title"]
    assert len(titles) == 1


@pytest.mark.django_db
def test_nontext_change_triggers_reapply_without_text_change():
    source, target = _create_source_and_target_pages("nontext")
    segments = PageTranslationEngine().collect_segments(source)
    _seed_memory(target, segments)  # all text is unchanged
    job = TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
    )
    engine = PageTranslationEngine(SuffixTranslationEngine())
    # Simulate a non-text block whose source value changed (new key vs memory).
    engine.collect_nontext_hashes = lambda page: {"body:ghost": "newhash"}
    processor = TranslationQueueProcessor(engine)

    processor.process_job(job)

    job.refresh_from_db()
    target.refresh_from_db()
    # No text needed translating, but the draft was still re-applied to sync the
    # non-text change rather than being skipped as a no-op.
    assert job.status == TranslationJob.Status.COMPLETED
    assert target.get_latest_revision() is not None


@pytest.mark.django_db
def test_incremental_prunes_removed_segment_from_memory():
    source, target = _create_source_and_target_pages("prune")
    segments = PageTranslationEngine().collect_segments(source)
    _seed_memory(target, segments)
    # A stale block lingering in memory that no longer exists on the source.
    TranslationSegment.objects.create(
        target_page=target,
        segment_key="body:ghost-block",
        source_hash=segment_hash("gone"),
        translation_hash=segment_hash("gone-translated"),
    )
    job = TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
    )
    processor = TranslationQueueProcessor(PageTranslationEngine(SuffixTranslationEngine()))

    processor.process_job(job)

    job.refresh_from_db()
    assert job.status == TranslationJob.Status.COMPLETED
    assert not TranslationSegment.objects.filter(
        target_page=target, segment_key="body:ghost-block"
    ).exists()
    # The real segments remain in memory.
    assert TranslationSegment.objects.filter(target_page=target).count() == len(segments)


@pytest.mark.django_db
def test_submit_stores_source_text_for_debug_view():
    source, target = _create_source_and_target_pages("debug")
    job = TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
    )
    processor = TranslationQueueProcessor(PageTranslationEngine(SuffixTranslationEngine()))

    processor.process_job(job)

    job.refresh_from_db()
    title_task = next(t for t in job.remote_tasks if t["key"] == "title")
    assert title_task["source_text"] == "Source debug"


@pytest.mark.django_db
def test_segment_details_pairs_sent_and_returned_text():
    source, target = _create_source_and_target_pages("segdetail")
    job = TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
        remote_tasks=[
            {
                "key": "title",
                "source_text": "Halló",
                "text": "Hello",
                "status": "completed",
                "task_id": "t1",
            },
            {
                "key": "body",
                "source_text": "Mál",
                "status": "failed",
                "skipped_reason": "SameLanguageError",
                "task_id": "t2",
            },
        ],
    )

    details = {d["key"]: d for d in job.segment_details}

    assert details["title"]["source_text"] == "Halló"
    assert details["title"]["translation"] == "Hello"
    assert details["body"]["translation"] == ""  # nothing came back
    assert details["body"]["skipped_reason"] == "SameLanguageError"


@pytest.mark.django_db
def test_queue_update_translation_creates_job_for_supported_pair():
    en = Locale.objects.create(language_code="en")
    source, target = _create_source_and_target_pages("upd")
    target.locale = en
    target.save()

    job = queue_update_translation(source, target)

    assert job is not None
    assert job.source_language == "is"
    assert job.target_language == "en"
    # No duplicate while one is in flight.
    assert queue_update_translation(source, target) is None


@pytest.mark.django_db
def test_queue_update_translation_skips_unsupported_pair():
    de = Locale.objects.create(language_code="de")
    source, target = _create_source_and_target_pages("unsupported")
    target.locale = de
    target.save()

    assert queue_update_translation(source, target) is None
    assert not TranslationJob.objects.filter(target_page=target).exists()


def _source_with_translation(suffix):
    en = Locale.objects.create(language_code="en")
    root = Page.get_first_root_node()
    source = Page(title="Heim", slug=f"heim-{suffix}")
    root.add_child(instance=source)
    target = Page(
        title="Home",
        slug=f"home-{suffix}",
        locale=en,
        translation_key=source.translation_key,
    )
    root.add_child(instance=target)
    return source, target


@pytest.mark.django_db
def test_enqueue_translation_updates_queues_for_translations():
    source, target = _source_with_translation("enq")

    jobs = enqueue_translation_updates(source)

    assert len(jobs) == 1
    assert TranslationJob.objects.filter(
        source_page=source, target_page=target
    ).exists()


@pytest.mark.django_db
def test_page_has_translation_targets_detects_supported_translations():
    source, target = _source_with_translation("has")
    assert page_has_translation_targets(source) is True
    # A page with no translations has nothing to update.
    lonely = Page(title="Stök", slug="stok-page")
    Page.get_first_root_node().add_child(instance=lonely)
    assert page_has_translation_targets(lonely) is False


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


@pytest.mark.django_db
def test_command_prunes_old_finished_jobs_but_keeps_memory(capsys):
    source, target = _create_source_and_target_pages("prune-old")
    old_job = TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
        status=TranslationJob.Status.COMPLETED,
    )
    recent_job = TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
        status=TranslationJob.Status.COMPLETED,
    )
    TranslationJob.objects.filter(pk=old_job.pk).update(
        completed_at=timezone.now() - timedelta(days=40)
    )
    TranslationJob.objects.filter(pk=recent_job.pk).update(
        completed_at=timezone.now() - timedelta(days=1)
    )
    TranslationSegment.objects.create(
        target_page=target, segment_key="title", source_hash="a", translation_hash="b"
    )

    call_command(
        "process_heimdallur_translation_queue",
        prune_completed_older_than_days=30,
        limit=0,
    )

    output = capsys.readouterr().out
    assert "Pruned 1 finished translation jobs." in output
    assert not TranslationJob.objects.filter(pk=old_job.pk).exists()
    assert TranslationJob.objects.filter(pk=recent_job.pk).exists()  # too recent
    # Translation memory is intentionally retained.
    assert TranslationSegment.objects.filter(target_page=target).count() == 1


@pytest.mark.django_db
def test_until_done_processes_queue_to_completion():
    from wagtail_heimdallur.management.commands.process_heimdallur_translation_queue import (  # noqa: E501
        Command,
    )

    source, target = _create_source_and_target_pages("until-done")
    job = TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
    )
    processor = TranslationQueueProcessor(
        PageTranslationEngine(SuffixTranslationEngine())
    )

    Command()._process_until_done(
        processor,
        {"limit": None, "poll_interval": 0, "max_passes": 10},
    )

    job.refresh_from_db()
    # One pass submits, the next polls + applies — the loop drains the queue.
    assert job.status == TranslationJob.Status.COMPLETED
    assert TranslationJob.objects.processable().count() == 0


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
