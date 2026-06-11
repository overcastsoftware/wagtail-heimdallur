from django.conf import settings
from wagtail import hooks


@hooks.register("construct_homepage_summary_items")
def add_malstadur_key_warning(request, items):
    if settings.MALSTADUR_API_KEY:
        return

    items.append(
        {
            "name": "Málstaður API key",
            "content": "MALSTADUR_API_KEY is not set; Heimdallur API calls will fail until credentials are provided.",
        }
    )
