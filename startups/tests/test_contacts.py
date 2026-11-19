import pytest

from startups.constants import ContactFoundVia, ContactRole, ContactStatus
from startups.contact_extraction import ContactCandidate
from startups.contacts import save_contacts
from startups.models import Contact, Startup

pytestmark = pytest.mark.django_db

EVIDENCE_URL = "https://acme.com/team"


def candidate(full_name="", role=ContactRole.OTHER, email="", profile_url=""):
    return ContactCandidate(full_name, role, email, profile_url, EVIDENCE_URL)


def test_new_candidates_are_created_with_their_evidence():
    startup = Startup.objects.create(name="Acme")

    created = save_contacts(
        startup, [candidate("Jane Roe", ContactRole.CEO)], ContactFoundVia.WEBSITE
    )

    assert created == 1
    jane = startup.contacts.get()
    assert (jane.full_name, jane.role, jane.found_via, jane.status, jane.evidence_url) == (
        "Jane Roe",
        ContactRole.CEO,
        ContactFoundVia.WEBSITE,
        ContactStatus.CANDIDATE,
        EVIDENCE_URL,
    )


def test_known_contact_only_gets_its_blank_fields_filled():
    startup = Startup.objects.create(name="Acme")
    Contact.objects.create(
        startup=startup,
        full_name="Jane Roe",
        role=ContactRole.FOUNDER,
        email="jane@acme.com",
        found_via=ContactFoundVia.MANUAL,
        status=ContactStatus.REJECTED,
    )

    created = save_contacts(
        startup,
        [candidate("jane roe", ContactRole.CEO, profile_url="https://linkedin.com/in/jane")],
        ContactFoundVia.WEBSITE,
    )

    jane = startup.contacts.get()
    assert created == 0
    assert jane.profile_url == "https://linkedin.com/in/jane"
    assert jane.email == "jane@acme.com"
    assert jane.role == ContactRole.FOUNDER
    assert jane.status == ContactStatus.REJECTED
    assert jane.found_via == ContactFoundVia.MANUAL


def test_contacts_of_other_startups_are_not_matched():
    other = Startup.objects.create(name="Other")
    Contact.objects.create(startup=other, email="hello@acme.com", found_via=ContactFoundVia.WEBSITE)
    startup = Startup.objects.create(name="Acme")

    created = save_contacts(
        startup,
        [candidate(email="hello@acme.com", role=ContactRole.GENERAL)],
        ContactFoundVia.WEBSITE,
    )

    assert created == 1
