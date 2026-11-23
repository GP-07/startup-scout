from datetime import timedelta

import pytest
from django.utils import timezone

from startups.constants import (
    ContactFoundVia,
    ContactRole,
    ContactStatus,
    InspectionStatus,
    OpeningOrigin,
    OpeningsStatus,
)
from startups.models import Analysis, Contact, JobOpening, Startup, WebsiteInspection

pytestmark = pytest.mark.django_db


def create_startup(name, openings_status=None):
    startup = Startup.objects.create(name=name)
    if openings_status:
        WebsiteInspection.objects.create(
            startup=startup, status=InspectionStatus.DONE, openings_status=openings_status
        )
    return startup


def add_opening(startup, title, days_ago=None, is_remote=None):
    JobOpening.objects.create(
        startup=startup,
        title=title,
        is_remote=is_remote,
        origin=OpeningOrigin.ASHBY,
        published_at=timezone.now() - timedelta(days=days_ago) if days_ago is not None else None,
    )


def annotated(startup, queryset_method):
    return getattr(Startup.objects, queryset_method)().get(pk=startup.pk)


def test_openings_annotations():
    startup = create_startup("Acme", OpeningsStatus.ACTIVE)
    add_opening(startup, "Backend Engineer", days_ago=3, is_remote=True)
    add_opening(startup, "Designer", days_ago=10)

    acme = annotated(startup, "with_openings")

    assert acme.openings_state == OpeningsStatus.ACTIVE
    assert acme.openings_count == 2
    assert (timezone.now() - acme.latest_opening_at).days == 3
    assert acme.has_remote_opening is True


def test_startup_never_inspected_has_no_openings_checked():
    acme = annotated(create_startup("Acme"), "with_openings")

    assert (acme.openings_state, acme.openings_count, acme.latest_opening_at) == (
        OpeningsStatus.NOT_CHECKED,
        0,
        None,
    )
    assert acme.has_remote_opening is False


@pytest.mark.parametrize(
    ("role", "status", "expected"),
    [
        (ContactRole.CTO, ContactStatus.CANDIDATE, (True, False)),
        (ContactRole.GENERAL, ContactStatus.CONFIRMED, (False, True)),
        (ContactRole.CEO, ContactStatus.REJECTED, (False, False)),
        (ContactRole.OTHER, ContactStatus.CANDIDATE, (False, False)),
    ],
)
def test_contact_kinds(role, status, expected):
    startup = create_startup("Acme")
    Contact.objects.create(
        startup=startup, role=role, status=status, found_via=ContactFoundVia.WEBSITE
    )

    acme = annotated(startup, "with_contact_kinds")

    assert (acme.has_person_contact, acme.has_general_contact) == expected


def test_analysis_state():
    startup = create_startup("Acme")
    Analysis.objects.create(startup=startup, title="Draft", body="...")
    Analysis.objects.create(startup=startup, title="Sent", body="...", sent_at=timezone.now())

    acme = annotated(startup, "with_analysis_state")

    assert (acme.has_analysis, acme.has_sent_analysis) == (True, True)


def test_admin_changelist_lists_startups_with_openings_first(admin_client):
    create_startup("Quiet")
    hiring = create_startup("Hiring", OpeningsStatus.ACTIVE)
    add_opening(hiring, "Engineer")

    response = admin_client.get("/admin/startups/startup/")

    listed_names = [startup.name for startup in response.context["cl"].result_list]
    assert listed_names == ["Hiring", "Quiet"]


def test_admin_changelist_filters_by_openings_status(admin_client):
    create_startup("Quiet", OpeningsStatus.NONE)
    create_startup("Hiring", OpeningsStatus.ACTIVE)

    response = admin_client.get(
        "/admin/startups/startup/",
        {"website_inspection__openings_status": OpeningsStatus.ACTIVE},
    )

    assert [startup.name for startup in response.context["cl"].result_list] == ["Hiring"]
