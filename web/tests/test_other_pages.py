from unittest import mock

from django.urls import reverse

from sources.constants import SourceKey, SourceRunStatus
from sources.models import Source, SourceRun
from startups.models import Startup
from web.tests.helpers import create_startup


def test_manual_entry_creates_the_startup_and_opens_it(logged_client):
    with mock.patch("web.views.startups.add_startup_manually") as add_startup_manually:
        startup = create_startup("Acme", "acme.com")
        add_startup_manually.return_value = mock.Mock(startup=startup, created=True)

        response = logged_client.post(
            reverse("web:startup_create"), {"website": "https://acme.com", "name": "Acme"}
        )

    add_startup_manually.assert_called_once_with("https://acme.com", name="Acme")
    assert response.status_code == 302
    assert response.url == reverse("web:startup_detail", args=[startup.pk])


def test_manual_entry_with_invalid_url_shows_the_error(logged_client):
    response = logged_client.post(reverse("web:startup_create"), {"website": "not a url"})

    assert response.status_code == 200
    assert not Startup.objects.exists()
    assert "dominio" in response.content.decode()


def test_duplicates_are_listed_compared_and_merged(logged_client):
    kept = create_startup("Acme", "acme.com")
    duplicate = create_startup("Acme", "acme.io", source_key=SourceKey.MANUAL)
    duplicate.possible_duplicate_of = kept
    duplicate.save()

    listing = logged_client.get(reverse("web:duplicate_list"))
    comparison = logged_client.get(reverse("web:duplicate_compare", args=[duplicate.pk]))
    merged = logged_client.post(
        reverse("web:duplicate_merge", args=[duplicate.pk]), {"keep": kept.pk}
    )

    assert b"acme.io" in listing.content
    assert b"acme.io" in comparison.content and b"acme.com" in comparison.content
    assert merged.url == reverse("web:startup_detail", args=[kept.pk])
    assert list(Startup.objects.values_list("pk", flat=True)) == [kept.pk]


def test_duplicate_can_be_dismissed(logged_client):
    kept = create_startup("Acme", "acme.com")
    other = create_startup("Acme", "acme.io", source_key=SourceKey.MANUAL)
    other.possible_duplicate_of = kept
    other.save()

    logged_client.post(reverse("web:duplicate_dismiss", args=[other.pk]))

    other.refresh_from_db()
    assert other.possible_duplicate_of is None


def test_runs_page_lists_the_last_runs_per_source(logged_client):
    SourceRun.objects.create(
        source=Source.objects.get(key=SourceKey.HACKER_NEWS),
        status=SourceRunStatus.FAILED,
        items_seen=12,
        items_new=3,
        error="Hacker News request failed: 503",
    )

    response = logged_client.get(reverse("web:run_list"))

    content = response.content.decode()
    assert "Hacker News request failed: 503" in content
    assert "HN Who is hiring" in content
