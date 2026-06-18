"""Core data models for Wagtail-Heimdallur proofreading results."""

from dataclasses import dataclass, field
from typing import List
import json

from django.db import models
from django.utils import timezone


@dataclass
class DiffAnnotation:
    """A single correction annotation with character positions.

    Attributes:
        orig_start_idx: Start index in the original text.
        orig_end_idx: End index in the original text.
        orig_string: The original substring being annotated.
        changed_start_idx: Start index in the corrected text.
        changed_end_idx: End index in the corrected text.
        changed_string: The corrected substring.
        change_type: Category of the change (e.g., "spelling", "grammar", "style").
    """

    orig_start_idx: int
    orig_end_idx: int
    orig_string: str
    changed_start_idx: int
    changed_end_idx: int
    changed_string: str
    change_type: str

    def to_dict(self) -> dict:
        """Serialize this annotation to a plain dictionary."""
        return {
            "orig_start_idx": self.orig_start_idx,
            "orig_end_idx": self.orig_end_idx,
            "orig_string": self.orig_string,
            "changed_start_idx": self.changed_start_idx,
            "changed_end_idx": self.changed_end_idx,
            "changed_string": self.changed_string,
            "change_type": self.change_type,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DiffAnnotation":
        """Deserialize a DiffAnnotation from a plain dictionary."""
        return cls(
            orig_start_idx=data["orig_start_idx"],
            orig_end_idx=data["orig_end_idx"],
            orig_string=data["orig_string"],
            changed_start_idx=data["changed_start_idx"],
            changed_end_idx=data["changed_end_idx"],
            changed_string=data["changed_string"],
            change_type=data["change_type"],
        )


@dataclass
class ProofreadingResult:
    """Complete proofreading result with original, corrected text and annotations.

    Attributes:
        original_text: The original text that was proofread.
        corrected_text: The corrected version of the text.
        annotations: List of DiffAnnotation objects describing individual changes.
    """

    original_text: str
    corrected_text: str
    annotations: List[DiffAnnotation] = field(default_factory=list)

    def to_json(self) -> str:
        """Serialize this result to a JSON string."""
        return json.dumps({
            "original_text": self.original_text,
            "corrected_text": self.corrected_text,
            "annotations": [a.to_dict() for a in self.annotations],
        })

    @classmethod
    def from_json(cls, json_str: str) -> "ProofreadingResult":
        """Deserialize a ProofreadingResult from a JSON string."""
        data = json.loads(json_str)
        return cls(
            original_text=data["original_text"],
            corrected_text=data["corrected_text"],
            annotations=[
                DiffAnnotation.from_dict(a) for a in data["annotations"]
            ],
        )


class TranslationJobQuerySet(models.QuerySet):
    """Query helpers for persisted page translation jobs."""

    def pending(self):
        return self.filter(status=TranslationJob.Status.QUEUED)

    def processable(self):
        return self.filter(
            status__in=[
                TranslationJob.Status.QUEUED,
                TranslationJob.Status.RUNNING,
            ]
        )


class TranslationJob(models.Model):
    """Durable status record for a queued page translation."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        COMPLETED_WITH_WARNINGS = (
            "completed_with_warnings",
            "Completed with warnings",
        )
        FAILED = "failed", "Failed"

    source_page = models.ForeignKey(
        "wagtailcore.Page",
        related_name="+",
        on_delete=models.CASCADE,
    )
    target_page = models.ForeignKey(
        "wagtailcore.Page",
        related_name="+",
        on_delete=models.CASCADE,
    )
    source_language = models.CharField(max_length=20)
    target_language = models.CharField(max_length=20)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    attempts = models.PositiveIntegerField(default=0)
    translated_fields = models.JSONField(default=list, blank=True)
    skipped_fields = models.JSONField(default=list, blank=True)
    error_message = models.TextField(blank=True)
    remote_task_id = models.CharField(max_length=255, blank=True)
    remote_tasks = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = TranslationJobQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.source_page_id}->{self.target_page_id} "
            f"{self.source_language}->{self.target_language} ({self.status})"
        )

    @property
    def remote_task_count(self) -> int:
        return len(self.remote_tasks)

    @property
    def completed_remote_task_count(self) -> int:
        return sum(
            1
            for task in self.remote_tasks
            if task.get("status") == "completed"
        )

    @property
    def remote_progress_percent(self) -> int | None:
        if not self.remote_tasks:
            return None
        progress_values = [
            100 if task.get("status") == "completed" else task.get("progress", 0)
            for task in self.remote_tasks
        ]
        return round(sum(progress_values) / len(progress_values))

    @property
    def remote_progress_label(self) -> str:
        if not self.remote_tasks:
            return "-"
        progress = self.remote_progress_percent
        return (
            f"{self.completed_remote_task_count}/{self.remote_task_count} "
            f"completed ({progress}%)"
        )

    def mark_running(self) -> None:
        self.status = self.Status.RUNNING
        self.attempts += 1
        self.started_at = timezone.now()
        self.error_message = ""
        self.save(
            update_fields=[
                "status",
                "attempts",
                "started_at",
                "error_message",
                "updated_at",
            ]
        )

    def mark_remote_tasks_submitted(self, remote_tasks: list[dict]) -> None:
        self.status = self.Status.RUNNING
        self.remote_tasks = remote_tasks
        self.remote_task_id = remote_tasks[0]["task_id"] if remote_tasks else ""
        self.error_message = ""
        self.save(
            update_fields=[
                "status",
                "remote_task_id",
                "remote_tasks",
                "error_message",
                "updated_at",
            ]
        )

    @staticmethod
    def _serialize_skipped_fields(result) -> list[dict[str, str]]:
        return [
            {"field_name": skipped.field_name, "error": skipped.error}
            for skipped in result.skipped_fields
        ]

    def mark_completed(self, result) -> None:
        self.status = (
            self.Status.COMPLETED_WITH_WARNINGS
            if result.completed_with_warnings
            else self.Status.COMPLETED
        )
        self.translated_fields = list(result.translated_fields)
        self.skipped_fields = self._serialize_skipped_fields(result)
        self.error_message = ""
        self.completed_at = timezone.now()
        self.save(
            update_fields=[
                "status",
                "translated_fields",
                "skipped_fields",
                "error_message",
                "completed_at",
                "updated_at",
            ]
        )

    def mark_failed(self, error: Exception | str, result=None) -> None:
        self.status = self.Status.FAILED
        self.error_message = str(error)
        if result is not None:
            self.translated_fields = list(result.translated_fields)
            self.skipped_fields = self._serialize_skipped_fields(result)
        else:
            self.translated_fields = []
            self.skipped_fields = []
        self.completed_at = timezone.now()
        self.save(
            update_fields=[
                "status",
                "error_message",
                "translated_fields",
                "skipped_fields",
                "completed_at",
                "updated_at",
            ]
        )

    def reset_for_retry(self) -> None:
        self.status = self.Status.QUEUED
        self.error_message = ""
        self.translated_fields = []
        self.skipped_fields = []
        self.remote_task_id = ""
        self.remote_tasks = []
        self.started_at = None
        self.completed_at = None
        self.save(
            update_fields=[
                "status",
                "error_message",
                "translated_fields",
                "skipped_fields",
                "remote_task_id",
                "remote_tasks",
                "started_at",
                "completed_at",
                "updated_at",
            ]
        )
