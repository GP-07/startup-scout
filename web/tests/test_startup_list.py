from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from sources.constants import SourceKey
from sources.models import Source, SourceRecord
from startups.constants import (
    ContactRole,
    ContactStatus,
    InspectionStatus,
    StartupStatus,
)
from startups.models import Startup, WebsiteInspection
from startups.status import discard_startup
from web.tests.helpers import create_contact, create_startup

LIST_URL = reverse("web:startup_list")


def listed_names(response):
    return [startup.name for startup in response.context["page_obj"]]


def test_pages_require_login(client, db):
    response = client.get(LIST_URL)

    assert response.status_code == 302
    assert "login" in response.url


def test_startups_with_hiring_signal_come_first_then_the_newest(logged_client):
    create_startup("Old quiet", "oldquiet.com")
    hiring = create_startup("Hiring", "hiring.com")
    WebsiteInspection.objects.create(
        startup=hiring, status=InspectionStatus.DONE, has_hiring_signal=True
    )
    create_startup("New quiet", "newquiet.com")

    response = logged_client.get(LIST_URL)

    assert response.status_code == 200
    assert listed_names(response) == ["Hiring", "New quiet", "Old quiet"]


def test_discarded_startups_are_hidden_unless_filtered(logged_client):
    create_startup("Kept", "kept.com")
    discard_startup(create_startup("Gone", "gone.com"), reason="Agency")

    assert listed_names(logged_client.get(LIST_URL)) == ["Kept"]
    filtered = logged_client.get(LIST_URL, {"status": StartupStatus.DISCARDED})
    assert listed_names(filtered) == ["Gone"]


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"q": "robot"}, ["Acme"]),
        ({"q": "beta.io"}, ["Beta"]),
        ({"source": SourceKey.MANUAL}, ["Beta"]),
        ({"country": "es"}, ["Acme"]),
        ({"hiring": "yes"}, ["Beta"]),
        ({"hiring": "no"}, ["Acme"]),
        ({"has_contact": "yes"}, ["Acme"]),
        ({"has_contact": "no"}, ["Beta"]),
    ],
)
def test_filters(logged_client, params, expected):
    acme = create_startup("Acme", "acme.com", description="Robots for warehouses", country="ES")
    create_contact(acme, role=ContactRole.CTO)
    beta = create_startup("Beta", "beta.io", source_key=SourceKey.MANUAL)
    WebsiteInspection.objects.create(
        startup=beta, status=InspectionStatus.DONE, has_hiring_signal=True
    )
    create_contact(beta, full_name="Rejected Person", status=ContactStatus.REJECTED)

    assert listed_names(logged_client.get(LIST_URL, params)) == expected


def test_since_filter_keeps_startups_seen_from_that_date(logged_client):
    old = create_startup("Old", "old.com")
    Startup.objects.filter(pk=old.pk).update(first_seen_at=timezone.now() - timedelta(days=10))
    create_startup("Recent", "recent.com")
    since = (timezone.now() - timedelta(days=2)).date().isoformat()

    assert listed_names(logged_client.get(LIST_URL, {"since": since})) == ["Recent"]


def test_htmx_request_renders_only_the_results(logged_client):
    create_startup("Acme", "acme.com")

    response = logged_client.get(LIST_URL, headers={"HX-Request": "true"})

    assert b"<html" not in response.content
    assert b"Acme" in response.content


def test_quick_discard_needs_a_reason_and_returns_the_row(logged_client):
    startup = create_startup("Acme", "acme.com")
    url = reverse("web:startup_discard", args=[startup.pk])

    rejected = logged_client.post(url, {"reason": ""}, headers={"HX-Request": "true"})
    accepted = logged_client.post(url, {"reason": "Agency"}, headers={"HX-Request": "true"})

    assert rejected.status_code == 400
    assert accepted.status_code == 200
    startup.refresh_from_db()
    assert startup.status == StartupStatus.DISCARDED
    assert b"Agency" in accepted.content


def test_rows_show_sources_and_hiring_origin(logged_client):
    startup = create_startup("Acme", "acme.com")
    SourceRecord.objects.create(
        source=Source.objects.get(key=SourceKey.HACKER_NEWS_HIRING),
        startup=startup,
        external_id="hiring-1",
        published_at=timezone.now(),
    )

    content = logged_client.get(LIST_URL).content.decode()

    assert "Hacker News" in content
    assert "HN Who is hiring" in content
