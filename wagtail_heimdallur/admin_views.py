"""Wagtail admin views for Wagtail-Heimdallur."""

import re

import django_filters
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView
from wagtail.admin.filters import DateRangePickerWidget, WagtailFilterSet
from wagtail.admin.views.reports import ReportView
from wagtail.admin.widgets.button import HeaderButton

from wagtail_heimdallur.models import TranslationJob

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def humanize_segment_key(key: str) -> str:
    """Turn a raw segment key into a readable label.

    ``body:4d02d85a-…-132ffb258c54:text`` -> ``body[4d02d85a].text`` — the field
    name leads, StreamField block ids are shortened into brackets, and struct
    child names read as dotted attributes.
    """
    parts = key.split(":")
    label = parts[0]
    for part in parts[1:]:
        if _UUID_RE.match(part):
            label += f"[{part[:8]}]"
        else:
            label += f".{part}"
    return label


def _language_choices(field_name: str):
    """Distinct language codes actually present on jobs, as filter choices."""

    def choices():
        values = (
            TranslationJob.objects.order_by(field_name)
            .values_list(field_name, flat=True)
            .distinct()
        )
        return [(value, value) for value in values if value]

    return choices


class TranslationJobFilterSet(WagtailFilterSet):
    """Filters for the translation queue report (rendered as the filter panel)."""

    created = django_filters.DateFromToRangeFilter(
        field_name="created_at__date",
        label=_("Created between"),
        widget=DateRangePickerWidget,
    )
    status = django_filters.ChoiceFilter(
        label=_("Status"),
        choices=TranslationJob.Status.choices,
    )
    source_language = django_filters.ChoiceFilter(
        label=_("Source language"),
        choices=_language_choices("source_language"),
    )
    target_language = django_filters.ChoiceFilter(
        label=_("Target language"),
        choices=_language_choices("target_language"),
    )

    class Meta:
        model = TranslationJob
        fields = ["status", "source_language", "target_language"]


class TranslationQueueReportView(ReportView):
    """Report showing persisted page translation jobs, with a filter panel."""

    page_title = _("Translation queue")
    header_icon = "tasks"
    results_template_name = "wagtail_heimdallur/admin/translation_queue_results.html"
    filterset_class = TranslationJobFilterSet
    paginate_by = 50

    list_export = ["id", "created_at", "status", "source_language", "target_language"]
    export_headings = {
        "id": _("#"),
        "created_at": _("Created"),
        "status": _("Status"),
        "source_language": _("Source language"),
        "target_language": _("Target language"),
    }

    def __init__(self, **kwargs):
        self.index_url = reverse("wagtail_heimdallur_admin:translation_queue")
        self.index_results_url = reverse(
            "wagtail_heimdallur_admin:translation_queue_results"
        )
        super().__init__(**kwargs)

    def get_queryset(self):
        return TranslationJob.objects.select_related(
            "source_page", "target_page"
        ).order_by("-created_at")


class TranslationJobDetailView(DetailView):
    """Per-job debug view: source text sent vs. translation returned per segment."""

    model = TranslationJob
    context_object_name = "job"
    template_name = "wagtail_heimdallur/admin/translation_queue_detail.html"

    def get_queryset(self):
        return TranslationJob.objects.select_related("source_page", "target_page")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        job = self.object
        title = _("Translation job #%(pk)d") % {"pk": job.pk}
        # Drive the same slim header the report uses (shown when breadcrumbs are
        # present in wagtailadmin/generic/base.html).
        context["header_title"] = title
        context["page_title"] = title
        context["header_icon"] = "tasks"
        queue_url = reverse("wagtail_heimdallur_admin:translation_queue")
        context["breadcrumbs_items"] = [
            {"url": reverse("wagtailadmin_home"), "label": _("Home")},
            {"url": queue_url, "label": _("Translation queue")},
            {"url": "", "label": "#%d" % job.pk},
        ]
        context["header_buttons"] = [
            HeaderButton(
                label=_("Back to translation queue"),
                url=queue_url,
                icon_name="arrow-left",
            ),
        ]
        context["segments"] = [
            {**segment, "label": humanize_segment_key(segment["key"])}
            for segment in job.segment_details
        ]
        return context
