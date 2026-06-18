"""Wagtail admin URLs for Wagtail-Heimdallur."""

from django.urls import path

from wagtail_heimdallur.admin_views import TranslationQueueReportView

app_name = "wagtail_heimdallur_admin"

urlpatterns = [
    path(
        "translation-queue/",
        TranslationQueueReportView.as_view(),
        name="translation_queue",
    ),
]
