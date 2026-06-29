"""Process queued Wagtail-Heimdallur page translation jobs."""

import time

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
        parser.add_argument(
            "--prune-completed-older-than-days",
            type=int,
            default=None,
            help=(
                "Delete completed/failed job records older than this many days "
                "before processing (translation memory is kept)."
            ),
        )
        parser.add_argument(
            "--until-done",
            action="store_true",
            help=(
                "Keep submitting and polling until no jobs remain to process "
                "(otherwise a single pass is made)."
            ),
        )
        parser.add_argument(
            "--poll-interval",
            type=float,
            default=5.0,
            help="Seconds to wait between passes when using --until-done.",
        )
        parser.add_argument(
            "--max-passes",
            type=int,
            default=1000,
            help="Safety cap on the number of passes when using --until-done.",
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

        prune_days = options["prune_completed_older_than_days"]
        if prune_days is not None:
            if prune_days < 0:
                raise CommandError(
                    "--prune-completed-older-than-days must not be negative."
                )
            pruned_count = processor.prune_completed_jobs(prune_days)
            self.stdout.write(f"Pruned {pruned_count} finished translation jobs.")

        if options["until_done"]:
            self._process_until_done(processor, options)
            return

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

    def _process_until_done(self, processor, options):
        """Submit and poll repeatedly until the queue drains (or the cap hits)."""
        poll_interval = options["poll_interval"]
        max_passes = options["max_passes"]
        total_processed = 0
        passes = 0
        while True:
            passes += 1
            total_processed += processor.process_queued(limit=options["limit"])
            remaining = TranslationJob.objects.processable().count()
            self.stdout.write(f"Pass {passes}: {remaining} translation jobs remain.")
            if remaining == 0:
                break
            if passes >= max_passes:
                self.stdout.write(
                    self.style.WARNING(
                        f"Stopped after {max_passes} passes with {remaining} "
                        "jobs still pending."
                    )
                )
                break
            if poll_interval > 0:
                time.sleep(poll_interval)

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {total_processed} job-passes over {passes} passes."
            )
        )
