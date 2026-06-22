"""URL configuration for Wagtail-Heimdallur."""

from django.urls import path

from wagtail_heimdallur.views import (
    ProofreadView,
    SupportedLanguagesView,
)

app_name = "wagtail_heimdallur"

urlpatterns = [
    path("api/heimdallur/proofread/", ProofreadView.as_view(), name="proofread"),
    path("api/heimdallur/languages/", SupportedLanguagesView.as_view(), name="languages"),
]
