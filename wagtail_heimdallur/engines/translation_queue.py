"""Processing for queued page translation jobs."""

from __future__ import annotations

from datetime import timedelta
import logging

from django.db import transaction
from django.utils import timezone

from wagtail_heimdallur.engines.page_translation import PageTranslationEngine
from wagtail_heimdallur.models import TranslationJob

logger = logging.getLogger(__name__)


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

            translated_texts = []
            updated_remote_tasks = []
            all_completed = True
            for remote_task in job.remote_tasks:
                remote_status = self.page_translation_engine.get_text_translation_status(
                    remote_task["task_id"],
                    source_language=job.source_language,
                    target_language=job.target_language,
                )
                updated_remote_tasks.append(
                    {
                        **remote_task,
                        "status": remote_status.status,
                        "progress": remote_status.progress,
                    }
                )
                if remote_status.status == "in_progress":
                    all_completed = False
                    continue
                if remote_status.status in {"failed", "not_found"}:
                    job.remote_tasks = updated_remote_tasks
                    job.save(update_fields=["remote_tasks", "updated_at"])
                    job.mark_failed(
                        remote_status.error
                        or remote_status.message
                        or f"Miðeind translation task {remote_status.status}."
                    )
                    return job
                if remote_status.status != "completed":
                    job.remote_tasks = updated_remote_tasks
                    job.save(update_fields=["remote_tasks", "updated_at"])
                    job.mark_failed(
                        f"Unexpected Miðeind translation task status: "
                        f"{remote_status.status}."
                    )
                    return job
                if remote_status.text is None:
                    job.remote_tasks = updated_remote_tasks
                    job.save(update_fields=["remote_tasks", "updated_at"])
                    job.mark_failed(
                        "Miðeind completed a translation task without result text."
                    )
                    return job
                translated_texts.append(remote_status.text)

            job.remote_tasks = updated_remote_tasks
            job.save(update_fields=["remote_tasks", "updated_at"])
            if not all_completed:
                return job

            result = self.page_translation_engine.apply_translated_texts(
                source_page,
                target_page,
                translated_texts,
            )
        except Exception as exc:
            logger.exception("Queued page translation job %s failed.", job.pk)
            job.mark_failed(exc)
            return job

        if result.skipped_fields and not result.translated_fields:
            logger.warning(
                "Queued page translation job %s failed: all fields were skipped.",
                job.pk,
            )
            job.mark_failed(
                "All translatable fields were skipped during page translation.",
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
