"""Process queued Wagtail-Heimdallur page translation jobs."""

from django.core.management.base import BaseCommand, CommandError

from wagtail_heimdallur.engines.translation_queue import TranslationQueueProcessor
from wagtail_heimdallur.models import TranslationJob


class Command(BaseCommand):
    help = "Process queued Wagtail-Heimdallur page translation jobs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of queued jobs to process.",
        )
        parser.add_argument(
            "--retry-failed",
            action="store_true",
            help="Requeue failed jobs before processing.",
        )
        parser.add_argument(
            "--retry-warnings",
            action="store_true",
            help="Requeue completed-with-warnings jobs before processing.",
        )
        parser.add_argument(
            "--retry-running",
            action="store_true",
            help="Requeue stale running jobs before processing.",
        )
        parser.add_argument(
            "--older-than-minutes",
            type=int,
            default=None,
            help="Only requeue running jobs older than this many minutes.",
        )

    def handle(self, *args, **options):
        processor = TranslationQueueProcessor()
        retry_statuses = []
        if options["retry_failed"]:
            retry_statuses.append(TranslationJob.Status.FAILED)
        if options["retry_warnings"]:
            retry_statuses.append(TranslationJob.Status.COMPLETED_WITH_WARNINGS)
        if options["retry_running"]:
            older_than_minutes = options["older_than_minutes"]
            if older_than_minutes is None or older_than_minutes <= 0:
                raise CommandError(
                    "--retry-running requires --older-than-minutes with a "
                    "positive value."
                )
            requeued_count = processor.requeue_jobs(
                [TranslationJob.Status.RUNNING],
                older_than_minutes=older_than_minutes,
            )
            self.stdout.write(
                "Requeued "
                f"{requeued_count} stale running translation jobs."
            )
        if retry_statuses:
            requeued_count = processor.requeue_jobs(retry_statuses)
            self.stdout.write(f"Requeued {requeued_count} translation jobs.")

        processable_count = TranslationJob.objects.processable().count()
        processed_count = processor.process_queued(
            limit=options["limit"],
        )
        remaining_count = TranslationJob.objects.processable().count()

        self.stdout.write(
            self.style.SUCCESS(
                "Processed "
                f"{processed_count} of {processable_count} translation jobs."
            )
        )
        if remaining_count:
            self.stdout.write(f"{remaining_count} translation jobs remain.")
