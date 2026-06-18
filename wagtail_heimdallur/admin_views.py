"""Wagtail admin views for Wagtail-Heimdallur."""

from django.views.generic import ListView

from wagtail_heimdallur.models import TranslationJob


class TranslationQueueReportView(ListView):
    """Report showing persisted page translation jobs."""

    model = TranslationJob
    context_object_name = "jobs"
    paginate_by = 50
    template_name = "wagtail_heimdallur/admin/translation_queue.html"

    def get_queryset(self):
        queryset = (
            TranslationJob.objects.select_related("source_page", "target_page")
            .order_by("-created_at")
        )
        status = self.request.GET.get("status")
        if status:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status"] = self.request.GET.get("status", "")
        context["status_choices"] = TranslationJob.Status.choices
        context["status_counts"] = {
            status: TranslationJob.objects.filter(status=status).count()
            for status, _label in TranslationJob.Status.choices
        }
        return context
