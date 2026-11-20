from datetime import date

from django.urls import reverse

from startups.constants import ContactFoundVia, ContactRole, ContactStatus, StartupStatus
from startups.models import Analysis, Contact
from web.tests.helpers import create_contact, create_startup


def detail_url(startup):
    return reverse("web:startup_detail", args=[startup.pk])


def test_detail_shows_data_provenance_contacts_and_history(logged_client):
    startup = create_startup("Acme", "acme.com", description="Robots")
    startup.field_sources = {"name": "hacker_news"}
    startup.save()
    create_contact(startup, full_name="Jane Roe", evidence_url="https://acme.com/team")

    response = logged_client.get(detail_url(startup))

    content = response.content.decode()
    assert response.status_code == 200
    assert "Acme" in content
    assert "acme.com" in content
    assert "Jane Roe" in content
    assert "https://acme.com/team" in content
    assert "Hacker News" in content


def test_status_change_from_the_detail(logged_client):
    startup = create_startup("Acme", "acme.com")
    url = reverse("web:startup_status", args=[startup.pk])

    response = logged_client.post(url, {"status": StartupStatus.REVIEWING, "note": "Promising"})

    assert response.status_code == 302
    startup.refresh_from_db()
    assert startup.status == StartupStatus.REVIEWING
    assert startup.status_changes.get().note == "Promising"


def test_discarding_from_the_detail_without_reason_is_refused(logged_client):
    startup = create_startup("Acme", "acme.com")
    url = reverse("web:startup_status", args=[startup.pk])

    response = logged_client.post(url, {"status": StartupStatus.DISCARDED, "note": ""}, follow=True)

    startup.refresh_from_db()
    assert startup.status == StartupStatus.NEW
    assert "motivo" in response.content.decode()


def test_contacts_are_confirmed_rejected_and_added_by_hand(logged_client):
    startup = create_startup("Acme", "acme.com")
    jane = create_contact(startup)
    review_url = reverse("web:contact_review", args=[jane.pk])

    confirmed = logged_client.post(
        review_url, {"status": ContactStatus.CONFIRMED}, headers={"HX-Request": "true"}
    )
    added = logged_client.post(
        reverse("web:contact_create", args=[startup.pk]),
        {"full_name": "John Doe", "role": ContactRole.CTO, "email": "john@acme.com"},
        headers={"HX-Request": "true"},
    )

    jane.refresh_from_db()
    assert jane.status == ContactStatus.CONFIRMED
    john = startup.contacts.get(full_name="John Doe")
    assert (john.found_via, john.status) == (ContactFoundVia.MANUAL, ContactStatus.CONFIRMED)
    assert confirmed.status_code == added.status_code == 200
    assert b"John Doe" in added.content


def test_contact_added_by_hand_needs_some_way_to_reach_it(logged_client):
    startup = create_startup("Acme", "acme.com")

    response = logged_client.post(
        reverse("web:contact_create", args=[startup.pk]),
        {"full_name": "", "role": ContactRole.CTO, "email": "", "profile_url": ""},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 400
    assert not Contact.objects.exists()


def test_analysis_lifecycle(logged_client):
    startup = create_startup("Acme", "acme.com")
    jane = create_contact(startup)

    created = logged_client.post(
        reverse("web:analysis_create", args=[startup.pk]),
        {"title": "Onboarding", "body": "## Idea\n\nShorter **signup**"},
    )
    analysis = startup.analyses.get()
    edited = logged_client.post(
        reverse("web:analysis_edit", args=[analysis.pk]),
        {"title": "Onboarding v2", "body": "## Idea\n\nShorter signup"},
    )
    sent = logged_client.post(
        reverse("web:analysis_mark_sent", args=[analysis.pk]),
        {"sent_on": "2026-11-20", "sent_to": jane.pk},
        headers={"HX-Request": "true"},
    )

    assert created.status_code == edited.status_code == 302
    analysis.refresh_from_db()
    startup.refresh_from_db()
    assert analysis.title == "Onboarding v2"
    assert analysis.sent_at.date() == date(2026, 11, 20)
    assert analysis.sent_to == jane
    assert startup.status == StartupStatus.CONTACTED
    assert sent.status_code == 200

    logged_client.post(
        reverse("web:analysis_unmark_sent", args=[analysis.pk]), headers={"HX-Request": "true"}
    )
    analysis.refresh_from_db()
    assert analysis.sent_at is None

    deleted = logged_client.post(
        reverse("web:analysis_delete", args=[analysis.pk]), headers={"HX-Request": "true"}
    )
    assert deleted.status_code == 200
    assert not Analysis.objects.exists()


def test_analysis_body_is_rendered_as_markdown_without_raw_html(logged_client):
    startup = create_startup("Acme", "acme.com")
    Analysis.objects.create(
        startup=startup, title="Ideas", body="**bold** <script>alert(1)</script>"
    )

    content = logged_client.get(detail_url(startup)).content.decode()

    assert "<strong>bold</strong>" in content
    assert "<script>alert(1)</script>" not in content
