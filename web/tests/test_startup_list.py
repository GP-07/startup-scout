from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from sources.constants import SourceKey
from startups.constants import (
    ContactRole,
    ContactStatus,
    InspectionStatus,
    OpeningOrigin,
    OpeningsStatus,
    StartupStatus,
)
from startups.models import Analysis, JobOpening, Startup, WebsiteInspection
from startups.status import discard_startup
from web.tests.helpers import create_contact, create_startup

LIST_URL = reverse("web:startup_list")
ALL = {"openings": "all"}


def listed_names(response):
    return [startup.name for startup in response.context["page_obj"]]


def set_openings(startup, status, *openings):
    """`openings` are (title, days_ago or None, is_remote) tuples."""
    WebsiteInspection.objects.update_or_create(
        startup=startup, defaults={"status": InspectionStatus.DONE, "openings_status": status}
    )
    for title, days_ago, is_remote in openings:
        JobOpening.objects.create(
            startup=startup,
            title=title,
            is_remote=is_remote,
            origin=OpeningOrigin.WEBSITE,
            published_at=timezone.now() - timedelta(days=days_ago)
            if days_ago is not None
            else None,
        )
    return startup


def sorted_names(client, params):
    """Names listed with these filters, among all startups whatever their openings."""
    return sorted(listed_names(client.get(LIST_URL, {**ALL, **params})))


def test_pages_require_login(client, db):
    response = client.get(LIST_URL)

    assert response.status_code == 302
    assert "login" in response.url


def test_default_list_shows_only_startups_with_active_openings_newest_opening_first(
    logged_client,
):
    set_openings(
        create_startup("Older opening", "older.com"), OpeningsStatus.ACTIVE, ("Engineer", 20, None)
    )
    set_openings(
        create_startup("Undated", "undated.com"), OpeningsStatus.ACTIVE, ("Designer", None, None)
    )
    set_openings(
        create_startup("Newest opening", "newest.com"), OpeningsStatus.ACTIVE, ("Engineer", 2, None)
    )
    set_openings(create_startup("No openings", "none.com"), OpeningsStatus.NONE)
    create_startup("No signal", "nosignal.com")

    response = logged_client.get(LIST_URL)

    assert listed_names(response) == ["Newest opening", "Older opening", "Undated"]


@pytest.mark.parametrize(
    ("openings_filter", "expected"),
    [
        (OpeningsStatus.UNVERIFIED, ["Unverified"]),
        (OpeningsStatus.NONE, ["No openings"]),
        (OpeningsStatus.NOT_CHECKED, ["No signal"]),
    ],
)
def test_openings_filter(logged_client, openings_filter, expected):
    set_openings(
        create_startup("Active", "active.com"), OpeningsStatus.ACTIVE, ("Engineer", 1, None)
    )
    set_openings(create_startup("Unverified", "unverified.com"), OpeningsStatus.UNVERIFIED)
    set_openings(create_startup("No openings", "none.com"), OpeningsStatus.NONE)
    create_startup("No signal", "nosignal.com")

    assert listed_names(logged_client.get(LIST_URL, {"openings": openings_filter})) == expected


def test_role_and_remote_filters_look_at_the_openings(logged_client):
    set_openings(
        create_startup("Backend remote", "a.com"),
        OpeningsStatus.ACTIVE,
        ("Senior Backend Engineer", 1, True),
    )
    set_openings(
        create_startup("Backend onsite", "b.com"),
        OpeningsStatus.ACTIVE,
        ("Backend Developer", 2, False),
    )
    set_openings(create_startup("Design", "c.com"), OpeningsStatus.ACTIVE, ("Designer", 3, True))

    assert listed_names(logged_client.get(LIST_URL, {"role": "backend"})) == [
        "Backend remote",
        "Backend onsite",
    ]
    assert listed_names(logged_client.get(LIST_URL, {"remote": "on"})) == [
        "Backend remote",
        "Design",
    ]
    assert listed_names(logged_client.get(LIST_URL, {"role": "backend", "remote": "on"})) == [
        "Backend remote"
    ]


def test_contact_filter(logged_client):
    create_contact(create_startup("Person", "a.com"), role=ContactRole.CTO)
    create_contact(create_startup("General", "b.com"), full_name="", role=ContactRole.GENERAL)
    create_contact(
        create_startup("Rejected", "c.com"), role=ContactRole.CEO, status=ContactStatus.REJECTED
    )

    assert sorted_names(logged_client, {"contact": "person"}) == ["Person"]
    assert sorted_names(logged_client, {"contact": "general"}) == ["General"]
    assert sorted_names(logged_client, {"contact": "none"}) == ["Rejected"]


def test_analysis_filter(logged_client):
    create_startup("Untouched", "a.com")
    Analysis.objects.create(startup=create_startup("Draft", "b.com"), title="Draft", body="...")
    Analysis.objects.create(
        startup=create_startup("Sent", "c.com"), title="Sent", body="...", sent_at=timezone.now()
    )

    assert sorted_names(logged_client, {"analysis": "none"}) == ["Untouched"]
    assert sorted_names(logged_client, {"analysis": "draft"}) == ["Draft"]
    assert sorted_names(logged_client, {"analysis": "sent"}) == ["Sent"]


def test_discarded_startups_are_hidden_unless_filtered(logged_client):
    create_startup("Kept", "kept.com")
    discard_startup(create_startup("Gone", "gone.com"), reason="Agency")

    assert listed_names(logged_client.get(LIST_URL, ALL)) == ["Kept"]
    filtered = logged_client.get(LIST_URL, {**ALL, "status": StartupStatus.DISCARDED})
    assert listed_names(filtered) == ["Gone"]


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"q": "robot"}, ["Acme"]),
        ({"q": "beta.io"}, ["Beta"]),
        ({"source": SourceKey.MANUAL}, ["Beta"]),
        ({"country": "es"}, ["Acme"]),
    ],
)
def test_text_source_and_country_filters(logged_client, params, expected):
    create_startup("Acme", "acme.com", description="Robots for warehouses", country="ES")
    create_startup("Beta", "beta.io", source_key=SourceKey.MANUAL)

    assert listed_names(logged_client.get(LIST_URL, {**ALL, **params})) == expected


def test_since_filter_keeps_startups_seen_from_that_date(logged_client):
    old = create_startup("Old", "old.com")
    Startup.objects.filter(pk=old.pk).update(first_seen_at=timezone.now() - timedelta(days=10))
    create_startup("Recent", "recent.com")
    since = (timezone.now() - timedelta(days=2)).date().isoformat()

    assert listed_names(logged_client.get(LIST_URL, {**ALL, "since": since})) == ["Recent"]


def test_rows_show_the_first_openings(logged_client):
    set_openings(
        create_startup("Acme", "acme.com"),
        OpeningsStatus.ACTIVE,
        ("Backend Engineer", 1, True),
        ("Designer", 2, None),
    )

    content = logged_client.get(LIST_URL).content.decode()

    assert "2 búsquedas" in content
    assert "Backend Engineer" in content
    assert "remoto" in content
    assert "Hacker News" in content


def test_htmx_request_renders_only_the_results(logged_client):
    create_startup("Acme", "acme.com")

    response = logged_client.get(LIST_URL, ALL, headers={"HX-Request": "true"})

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
