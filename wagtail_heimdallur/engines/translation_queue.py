"""Processing for queued page translation jobs."""

from __future__ import annotations

from datetime import timedelta
import logging

from django.db import transaction
from django.utils import timezone

from wagtail_heimdallur.engines.page_translation import (
    PageTranslationEngine,
    PageTranslationResult,
    SkippedField,
    segment_hash,
)
from wagtail_heimdallur.models import TranslationJob, TranslationSegment

logger = logging.getLogger(__name__)


def _segment_label(text: str, index: int) -> str:
    """A readable label for a text segment that could not be translated."""
    text = (text or "").strip()
    if not text:
        return f"segment {index + 1}"
    return text[:60] + ("…" if len(text) > 60 else "")


def _target_revision_object(job):
    """The translated page as it currently stands — its latest *draft* revision.

    Translations are saved as drafts (never auto-published), so the live page row
    is usually still the untranslated copy. Reading the live page would make every
    "unchanged" block fall back to the source language; the latest revision is the
    real current translation we must preserve.
    """
    target = job.target_page.specific
    getter = getattr(target, "get_latest_revision_as_object", None)
    if getter is None:
        return target
    try:
        return getter() or target
    except Exception:  # pragma: no cover - defensive
        return target


def _load_memory(target_page) -> dict[str, tuple[str, str]]:
    """Per-block translation memory for a target page: key -> (src, translation)."""
    return {
        segment.segment_key: (segment.source_hash, segment.translation_hash)
        for segment in TranslationSegment.objects.filter(target_page=target_page)
    }


def _save_memory(
    target_page,
    memory_updates: dict[str, tuple[str, str]],
    source_keys: set[str],
) -> None:
    """Upsert hashes for re-translated blocks and prune blocks no longer present."""
    for key, (source_hash, translation_hash) in memory_updates.items():
        TranslationSegment.objects.update_or_create(
            target_page=target_page,
            segment_key=key,
            defaults={
                "source_hash": source_hash,
                "translation_hash": translation_hash,
            },
        )
    TranslationSegment.objects.filter(target_page=target_page).exclude(
        segment_key__in=source_keys
    ).delete()


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
            target_page = _target_revision_object(job)
            if should_submit:
                return self._submit(job, source_page, target_page)

            # Poll every outstanding task before deciding anything. A task that
            # fails on its own (e.g. Miðeind's SameLanguageError when a segment is
            # already in the target language) does not fail the whole page — that
            # segment is skipped and its original/existing text kept.
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

            return self._finalize(job, source_page, target_page)
        except Exception as exc:
            logger.exception("Queued page translation job %s failed.", job.pk)
            job.mark_failed(exc)
            return job

    def _submit(self, job, source_page, target_page) -> TranslationJob:
        """Submit one async task per *changed* segment (incremental).

        Unchanged segments (their source still hashes to what we last translated)
        are skipped entirely, preserving any human correction on the target.
        """
        engine = self.page_translation_engine
        source_segments = engine.collect_segments(source_page)
        if not source_segments:
            raise ValueError("Page has no non-empty text values to translate.")

        memory = _load_memory(target_page)
        target_texts = dict(engine.collect_segments(target_page))

        remote_tasks = []
        replaced_edits = []
        for index, (key, text) in enumerate(source_segments):
            source_hash = segment_hash(text)
            known = memory.get(key)
            if known is not None and known[0] == source_hash:
                continue  # source unchanged — leave the target block alone

            task_id = engine.start_text_translation(
                text,
                source_language=job.source_language,
                target_language=job.target_language,
            )
            remote_tasks.append(
                {
                    "index": index,
                    "key": key,
                    "task_id": task_id,
                    "status": "in_progress",
                    "source_hash": source_hash,
                    # Kept for the queue detail view so the exact text sent to the
                    # backend can be compared against what came back.
                    "source_text": text,
                }
            )
            # Changed source AND the existing translation was hand-edited: we will
            # re-translate it, but flag it so the reviewer can reconcile.
            if (
                known is not None
                and key in target_texts
                and segment_hash(target_texts[key]) != known[1]
            ):
                replaced_edits.append(
                    {
                        "field_name": _segment_label(text, index),
                        "previous": target_texts[key],
                    }
                )

        job.replaced_edits = replaced_edits

        if remote_tasks:
            job.mark_remote_tasks_submitted(remote_tasks)
            job.save(update_fields=["replaced_edits", "updated_at"])
            return job

        # No text to translate, but we still rebuild the draft when the structure
        # changed (blocks removed) or a non-text value (chooser/embed/number)
        # changed on the source — so those stay in sync. A true no-op is skipped
        # to avoid resetting the target or spamming revisions.
        source_keys = {key for key, _ in source_segments}
        nontext_hashes = engine.collect_nontext_hashes(source_page)
        all_source_keys = source_keys | set(nontext_hashes)
        removed = set(memory) - all_source_keys
        nontext_changed = any(
            memory.get(key) is None or memory[key][0] != value_hash
            for key, value_hash in nontext_hashes.items()
        )
        if removed or nontext_changed:
            return self._finalize(job, source_page, target_page)

        job.mark_completed(PageTranslationResult())
        return job

    def _finalize(self, job, source_page, target_page) -> TranslationJob:
        """Apply results as a draft, preserving unchanged blocks, update memory."""
        engine = self.page_translation_engine
        memory = _load_memory(target_page)
        completed_tasks = {
            task["key"]: task for task in job.remote_tasks if "key" in task
        }
        source_segments = engine.collect_segments(source_page)
        source_keys = {key for key, _ in source_segments}
        target_texts = dict(engine.collect_segments(target_page))

        resolved: dict[str, str] = {}
        memory_updates: dict[str, tuple[str, str]] = {}
        skipped: list[SkippedField] = []
        translated_ok = 0
        for index, (key, source_text) in enumerate(source_segments):
            task = completed_tasks.get(key)
            if task is not None and "text" in task:
                resolved[key] = task["text"]
                memory_updates[key] = (
                    segment_hash(source_text),
                    segment_hash(task["text"]),
                )
                translated_ok += 1
            elif task is not None:
                # Attempted but skipped/failed: keep the existing target text.
                resolved[key] = target_texts.get(key, source_text)
                skipped.append(
                    SkippedField(
                        _segment_label(source_text, index),
                        task.get("skipped_reason", "Not translated."),
                    )
                )
            else:
                # Unchanged: preserve whatever is on the target (incl. edits).
                resolved[key] = target_texts.get(key, source_text)

        result = engine.apply_resolved_segments(
            source_page,
            target_page,
            resolved,
            nontext_memory=memory,
            replaced_edits=job.replaced_edits,
        )
        result.skipped_fields.extend(skipped)
        # Persist text + non-text memory, keeping every key currently present so
        # the prune only drops blocks that were actually removed.
        memory_updates.update(result.nontext_updates)
        keep_keys = source_keys | result.nontext_keys
        _save_memory(target_page, memory_updates, keep_keys)

        # Only a wholesale failure (every attempted segment failed and nothing
        # else exists) marks the job failed; a partial failure completes with
        # warnings so the rest of the page still updates.
        if (
            skipped
            and translated_ok == 0
            and len(skipped) == len(source_segments)
        ):
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

    def prune_completed_jobs(self, older_than_days: int) -> int:
        """Delete finished job records older than the cutoff.

        Only the job history is removed — TranslationSegment rows are the
        translation memory and are kept (they are pruned per page as content
        changes, and cascade when a page is deleted).
        """
        cutoff = timezone.now() - timedelta(days=older_than_days)
        jobs = TranslationJob.objects.filter(
            status__in=[
                TranslationJob.Status.COMPLETED,
                TranslationJob.Status.COMPLETED_WITH_WARNINGS,
                TranslationJob.Status.FAILED,
            ],
            completed_at__lte=cutoff,
        )
        pruned, _ = jobs.delete()
        return pruned
