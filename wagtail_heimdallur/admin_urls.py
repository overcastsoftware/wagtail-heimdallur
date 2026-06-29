"""Wagtail admin URLs for Wagtail-Heimdallur."""

from django.urls import path

from wagtail_heimdallur.admin_views import (
    TranslationJobDetailView,
    TranslationQueueReportView,
)

app_name = "wagtail_heimdallur_admin"

urlpatterns = [
    path(
        "translation-queue/",
        TranslationQueueReportView.as_view(),
        name="translation_queue",
    ),
    path(
        "translation-queue/results/",
        TranslationQueueReportView.as_view(results_only=True),
        name="translation_queue_results",
    ),
    path(
        "translation-queue/<int:pk>/",
        TranslationJobDetailView.as_view(),
        name="translation_queue_detail",
    ),
]
