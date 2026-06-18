"""Processing for queued page translation jobs."""

from __future__ import annotations

import logging

from django.db import transaction

from wagtail_heimdallur.engines.page_translation import PageTranslationEngine
from wagtail_heimdallur.models import TranslationJob

logger = logging.getLogger(__name__)


class TranslationQueueProcessor:
    """Process persisted page translation jobs."""

    def __init__(self, page_translation_engine: PageTranslationEngine | None = None):
        self.page_translation_engine = page_translation_engine or PageTranslationEngine()

    def process_queued(self, limit: int | None = None) -> int:
        """Process queued jobs and return the number attempted."""
        queryset = TranslationJob.objects.pending().order_by("created_at")
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
            if job.status != TranslationJob.Status.QUEUED:
                return job
            job.mark_running()

        try:
            source_page = job.source_page.specific
            target_page = job.target_page.specific
            result = self.page_translation_engine.translate_page(
                source_page,
                target_page,
                source_language=job.source_language,
                target_language=job.target_language,
            )
        except Exception as exc:
            logger.exception("Queued page translation job %s failed.", job.pk)
            job.mark_failed(exc)
            return job

        job.mark_completed(result)
        return job
