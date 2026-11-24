from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command

from sources.constants import SourceKey
from sources.models import Source
from startups.blacklist import blacklist_startup
from startups.constants import (
    BLACKLIST_DEFAULT_REASON,
    InspectionStatus,
    OpeningOrigin,
    OpeningsStatus,
    StartupStatus,
)
from startups.ingestion import StartupIngestionService
from startups.models import BlacklistedDomain, JobOpening, Startup, StartupDomain, WebsiteInspection
from startups.openings import startups_to_verify
from startups.tasks import enqueue_website_inspection
from startups.tests.fakes import FakeRedirectResolver, build_raw_startup

pytestmark = pytest.mark.django_db


def create_job_board(domain="jobsboard.com"):
    startup = Startup.objects.create(name="Jobs Board", website=f"https://{domain}")
    StartupDomain.objects.create(startup=startup, domain=domain, is_primary=True)
    StartupDomain.objects.create(startup=startup, domain=f"old-{domain}")
    WebsiteInspection.objects.create(
        startup=startup,
        status=InspectionStatus.DONE,
        has_hiring_signal=True,
        openings_status=OpeningsStatus.ACTIVE,
    )
    JobOpening.objects.create(
        startup=startup, title="Backend Engineer at Acme", origin=OpeningOrigin.WEBSITE
    )
    return startup


def test_blacklisting_a_startup_keeps_its_domains_discards_it_and_drops_its_openings():
    startup = create_job_board()

    blacklist_startup(startup)

    startup.refresh_from_db()
    assert set(BlacklistedDomain.objects.values_list("domain", flat=True)) == {
        "jobsboard.com",
        "old-jobsboard.com",
    }
    assert startup.status == StartupStatus.DISCARDED
    assert startup.discard_reason == BLACKLIST_DEFAULT_REASON
    assert not startup.job_openings.exists()
    assert startup.website_inspection.openings_status == OpeningsStatus.NONE


def test_blacklisting_twice_keeps_one_entry_per_domain():
    startup = create_job_board()

    blacklist_startup(startup, reason="Agregador")
    blacklist_startup(startup, reason="Agregador")

    assert BlacklistedDomain.objects.count() == 2
    assert BlacklistedDomain.objects.first().reason == "Agregador"


def test_a_blacklisted_site_reported_again_by_a_source_comes_in_discarded():
    BlacklistedDomain.objects.create(domain="jobsboard.com", reason=BLACKLIST_DEFAULT_REASON)
    service = StartupIngestionService(redirect_resolver=FakeRedirectResolver())
    source = Source.objects.get(key=SourceKey.HACKER_NEWS)

    result = service.ingest(
        source, build_raw_startup("hn-9", "Jobs Board", website="https://jobsboard.com/")
    )

    assert result.created
    assert result.startup.status == StartupStatus.DISCARDED
    assert result.startup.discard_reason == BLACKLIST_DEFAULT_REASON


def test_discarded_startups_are_neither_inspected_nor_verified():
    startup = create_job_board()
    blacklist_startup(startup)

    with mock.patch("startups.tasks.inspect_website_task") as inspect_task:
        enqueue_website_inspection(startup)

    inspect_task.assert_not_called()
    assert startup not in startups_to_verify(include_checked=True)


def test_blacklist_domain_command_blacklists_the_startup_of_a_domain():
    startup = create_job_board()
    output = StringIO()

    call_command("blacklist_domain", "https://www.jobsboard.com/jobs", stdout=output)

    startup.refresh_from_db()
    assert startup.status == StartupStatus.DISCARDED
    assert BlacklistedDomain.objects.filter(domain="jobsboard.com").exists()
    assert "Jobs Board" in output.getvalue()


def test_blacklist_domain_command_accepts_a_domain_without_startup():
    call_command("blacklist_domain", "otherboard.io", stdout=StringIO())

    assert BlacklistedDomain.objects.filter(domain="otherboard.io").exists()
