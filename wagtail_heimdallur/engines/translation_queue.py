"""Processing for queued page translation jobs."""

from __future__ import annotations

from datetime import timedelta
import logging

from django.db import transaction
from django.utils import timezone

from wagtail_heimdallur.engines.page_translation import (
    PageTranslationEngine,
    SkippedField,
)
from wagtail_heimdallur.models import TranslationJob

logger = logging.getLogger(__name__)


def _segment_label(text: str, index: int) -> str:
    """A readable label for a text segment that could not be translated."""
    text = (text or "").strip()
    if not text:
        return f"segment {index + 1}"
    return text[:60] + ("…" if len(text) > 60 else "")


class TranslationQueueProcessor:
    """Process persisted page translation jobs."""

    def __init__(self, page_translation_engine: PageTranslationEngine | None = None):
        self.page_translation_engine = page_translation_engine or PageTranslationEngine()

    def process_queued(self, limit: int | None = None) -> int:
        """Process queued jobs and return the number attempted."""
        queryset = TranslationJob.objects.processable().order_by("created_at")
        if limit is not None:
            queryset = queryset[:limit]

        processed = 0
        for job in queryset:
            self.process_job(job)
            processed += 1

        return processed

    def process_job(self, job: TranslationJob) -> TranslationJob:
        """Process a single translation job."""
        with transaction.atomic():
            job = TranslationJob.objects.select_for_update().get(pk=job.pk)
            if job.status not in {
                TranslationJob.Status.QUEUED,
                TranslationJob.Status.RUNNING,
            }:
                return job
            should_submit = (
                job.status == TranslationJob.Status.QUEUED
                or not job.remote_tasks
            )
            if should_submit:
                job.mark_running()

        try:
            source_page = job.source_page.specific
            target_page = job.target_page.specific
            if should_submit:
                texts = self.page_translation_engine.collect_texts(source_page)
                if not texts:
                    raise ValueError("Page has no non-empty text values to translate.")
                remote_tasks = []
                for index, text in enumerate(texts):
                    task_id = self.page_translation_engine.start_text_translation(
                        text,
                        source_language=job.source_language,
                        target_language=job.target_language,
                    )
                    remote_tasks.append(
                        {
                            "index": index,
                            "task_id": task_id,
                            "status": "in_progress",
                        }
                    )
                job.mark_remote_tasks_submitted(remote_tasks)
                return job

            # Poll every task before deciding anything. A task that fails on its
            # own (e.g. Miðeind's SameLanguageError when a segment is already in
            # the target language) does not fail the whole page — that segment is
            # skipped and its original text kept.
            updated_remote_tasks = []
            all_completed = True
            for remote_task in job.remote_tasks:
                remote_status = self.page_translation_engine.get_text_translation_status(
                    remote_task["task_id"],
                    source_language=job.source_language,
                    target_language=job.target_language,
                )
                entry = {
                    **remote_task,
                    "status": remote_status.status,
                    "progress": remote_status.progress,
                }
                if remote_status.status == "in_progress":
                    all_completed = False
                elif (
                    remote_status.status == "completed"
                    and remote_status.text is not None
                ):
                    entry["text"] = remote_status.text
                else:
                    entry["skipped_reason"] = (
                        remote_status.error
                        or remote_status.message
                        or f"Miðeind translation task {remote_status.status}."
                    )
                updated_remote_tasks.append(entry)

            job.remote_tasks = updated_remote_tasks
            job.save(update_fields=["remote_tasks", "updated_at"])
            if not all_completed:
                return job

            # All tasks finished: resolve each segment to its translation, or to
            # the original text when it could not be translated.
            original_texts = self.page_translation_engine.collect_texts(source_page)
            resolved_texts = []
            skipped = []
            for entry in sorted(updated_remote_tasks, key=lambda task: task["index"]):
                if "text" in entry:
                    resolved_texts.append(entry["text"])
                    continue
                index = entry["index"]
                original = (
                    original_texts[index] if index < len(original_texts) else ""
                )
                resolved_texts.append(original)
                skipped.append(
                    SkippedField(
                        field_name=_segment_label(original, index),
                        error=entry.get("skipped_reason", "Not translated."),
                    )
                )

            result = self.page_translation_engine.apply_translated_texts(
                source_page,
                target_page,
                resolved_texts,
            )
            result.skipped_fields.extend(skipped)
        except Exception as exc:
            logger.exception("Queued page translation job %s failed.", job.pk)
            job.mark_failed(exc)
            return job

        if skipped and len(skipped) == len(resolved_texts):
            logger.warning(
                "Queued page translation job %s: no segments could be translated.",
                job.pk,
            )
            job.mark_failed(
                "No text segments could be translated.",
                result=result,
            )
            return job

        job.mark_completed(result)
        return job

    def requeue_jobs(
        self,
        statuses: list[str],
        older_than_minutes: int | None = None,
    ) -> int:
        """Reset jobs with the supplied statuses so they can be processed again."""
        jobs = TranslationJob.objects.filter(status__in=statuses)
        if older_than_minutes is not None:
            cutoff = timezone.now() - timedelta(minutes=older_than_minutes)
            jobs = jobs.filter(updated_at__lte=cutoff)

        requeued = 0
        for job in jobs:
            job.reset_for_retry()
            requeued += 1
        return requeued
