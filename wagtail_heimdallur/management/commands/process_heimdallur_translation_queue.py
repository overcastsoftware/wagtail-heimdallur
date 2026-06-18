"""Process queued Wagtail-Heimdallur page translation jobs."""

from django.core.management.base import BaseCommand

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

    def handle(self, *args, **options):
        queued_count = TranslationJob.objects.pending().count()
        processed_count = TranslationQueueProcessor().process_queued(
            limit=options["limit"],
        )
        remaining_count = TranslationJob.objects.pending().count()

        self.stdout.write(
            self.style.SUCCESS(
                "Processed "
                f"{processed_count} of {queued_count} queued translation jobs."
            )
        )
        if remaining_count:
            self.stdout.write(f"{remaining_count} queued translation jobs remain.")
