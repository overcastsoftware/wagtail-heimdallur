"""Tests for the translation queue report filters."""

import pytest
from wagtail.models import Page

from wagtail_heimdallur.admin_views import (
    TranslationJobFilterSet,
    humanize_segment_key,
)
from wagtail_heimdallur.models import TranslationJob


def test_humanize_segment_key():
    assert humanize_segment_key("title") == "title"
    assert (
        humanize_segment_key("body:4d02d85a-9746-4ff1-9cb8-132ffb258c54:text")
        == "body[4d02d85a].text"
    )
    # Struct child names read as dotted attributes; ids become bracketed.
    assert (
        humanize_segment_key("body:11111111-2222-3333-4444-555555555555:intro")
        == "body[11111111].intro"
    )


@pytest.mark.django_db
def test_filterset_filters_jobs():
    root = Page.get_first_root_node()
    source = Page(title="S", slug="report-source")
    target = Page(title="T", slug="report-target")
    root.add_child(instance=source)
    root.add_child(instance=target)

    done = TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="en",
        status=TranslationJob.Status.COMPLETED,
    )
    queued = TranslationJob.objects.create(
        source_page=source,
        target_page=target,
        source_language="is",
        target_language="de",
        status=TranslationJob.Status.QUEUED,
    )
    queryset = TranslationJob.objects.all()

    by_status = TranslationJobFilterSet({"status": "completed"}, queryset=queryset)
    assert list(by_status.qs) == [done]

    by_target = TranslationJobFilterSet({"target_language": "de"}, queryset=queryset)
    assert list(by_target.qs) == [queued]
