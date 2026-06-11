from django.conf import settings
from wagtail import hooks
from wagtail.admin.site_summary import SummaryItem


class MalstadurApiKeySummaryItem(SummaryItem):
    order = 10
    template_name = "home/malstadur_api_key_summary.html"

    def is_shown(self):
        return not settings.MALSTADUR_API_KEY


@hooks.register("construct_homepage_summary_items")
def add_malstadur_key_warning(request, items):
    items.append(MalstadurApiKeySummaryItem(request))
