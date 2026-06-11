"""Seed the demo site with locales and Icelandic sample content."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from home.models import HomePage
from wagtail.models import Locale, Page, Site


class Command(BaseCommand):
    help = "Create Wagtail locales, a demo site, and sample Icelandic content."

    def handle(self, *args, **options):
        icelandic, _ = Locale.objects.get_or_create(language_code="is")
        english, _ = Locale.objects.get_or_create(language_code="en")
        self.stdout.write(f"Locales ready: {icelandic.language_code}, {english.language_code}")

        root = Page.get_first_root_node()
        homepage = self._get_or_create_homepage(root, icelandic)

        Site.objects.exclude(hostname="localhost", port=8000).update(
            is_default_site=False,
        )
        demo_site, _ = Site.objects.update_or_create(
            hostname="localhost",
            port=8000,
            defaults={
                "site_name": "Wagtail-Heimdallur Demo",
                "root_page": homepage,
                "is_default_site": True,
            },
        )
        Site.objects.exclude(pk=demo_site.pk).update(is_default_site=False)
        self._ensure_admin_user()
        self.stdout.write(self.style.SUCCESS("Demo site ready."))

    def _get_or_create_homepage(self, root, locale):
        existing = HomePage.objects.filter(slug="heimdallur-synisida").first()
        if existing:
            existing.title = "Heimdallur sýnisíða"
            existing.locale = locale
            existing.body = (
                "<p>Þetta er íslenskur sýnitexti fyrir prófarkalestur og þýðingu.</p>"
            )
            existing.save_revision().publish()
            return existing

        homepage = HomePage(
            title="Heimdallur sýnisíða",
            slug="heimdallur-synisida",
            locale=locale,
            body="<p>Þetta er íslenskur sýnitexti fyrir prófarkalestur og þýðingu.</p>",
        )
        root.add_child(instance=homepage)
        homepage.save_revision().publish()
        return homepage

    def _ensure_admin_user(self):
        User = get_user_model()
        user, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@example.com",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created:
            user.set_password("admin")
            user.save()
            self.stdout.write("Created demo admin user: admin / admin")
