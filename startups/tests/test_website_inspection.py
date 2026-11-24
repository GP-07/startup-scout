from unittest import mock

import httpx
import pytest

from sources.constants import SourceKey
from sources.models import Source
from startups.constants import (
    CONTACT_FALLBACK_PATHS,
    CONTACT_MAX_EXTRA_PAGES,
    ContactFoundVia,
    ContactRole,
    ContactStatus,
    HiringSignalKind,
    HiringSignalMethod,
    InspectionStatus,
    OpeningsStatus,
)
from startups.ingestion import StartupIngestionService
from startups.models import WebsiteInspection
from startups.tests.fakes import FakeRedirectResolver, build_raw_startup
from startups.website_inspection import WebsiteInspectionService, mark_inspection_pending

pytestmark = pytest.mark.django_db

HOME_WITHOUT_SIGNAL = "<html><body><h1>Acme</h1><p>Robots for warehouses</p></body></html>"
HOME_WITH_SIGNAL = '<html><body><footer><a href="/careers">Careers</a></footer></body></html>'
CAREERS_PAGE = "<html><body><h1>Open positions</h1><p>Backend engineer</p></body></html>"
ALLOW_ALL_ROBOTS = "User-agent: *\nAllow: /\n"


class FakeSite:
    """Serves fixed pages per path and records every requested path."""

    def __init__(self, pages, robots=ALLOW_ALL_ROBOTS, redirects=None):
        self.pages = pages
        self.robots = robots
        self.redirects = redirects or {}
        self.requested_paths = []

    def __call__(self, request):
        path = request.url.path
        self.requested_paths.append(path)
        if path == "/robots.txt":
            if self.robots is None:
                return httpx.Response(404)
            return httpx.Response(200, text=self.robots)
        if path in self.redirects:
            return httpx.Response(302, headers={"Location": self.redirects[path]})
        if path in self.pages:
            return httpx.Response(
                200, text=self.pages[path], headers={"Content-Type": "text/html; charset=utf-8"}
            )
        return httpx.Response(404)


def hiring_requests(site):
    """The requests made for the hiring signal, leaving out the contact pages visited after."""
    contact_paths = set(CONTACT_FALLBACK_PATHS)
    return [path for path in site.requested_paths if path not in contact_paths]


def unreachable_site(request):
    raise httpx.ConnectError("unreachable", request=request)


def build_service(handler, openings_verifier=None):
    """The openings check has its own tests: here it is a mock unless one is given."""
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return WebsiteInspectionService(
        http_client=client, openings_verifier=openings_verifier or mock.Mock()
    )


def create_startup(website="https://acme.com"):
    source = Source.objects.get(key=SourceKey.HACKER_NEWS)
    service = StartupIngestionService(redirect_resolver=FakeRedirectResolver())
    return service.ingest(source, build_raw_startup("hn-1", "Acme", website=website)).startup


def test_signal_on_home_needs_a_single_page_request():
    site = FakeSite({"/": HOME_WITH_SIGNAL})

    inspection = build_service(site).inspect(create_startup())

    assert inspection.status == InspectionStatus.DONE
    assert inspection.has_hiring_signal is True
    assert inspection.hiring_signal_method == HiringSignalMethod.HOME
    assert inspection.hiring_signal_kind == HiringSignalKind.LINK_PATH
    assert inspection.hiring_signal_url == "https://acme.com/careers"
    assert inspection.inspected_at is not None
    assert hiring_requests(site) == ["/robots.txt", "/"]


def test_falls_back_to_typical_paths_when_home_has_no_signal():
    site = FakeSite({"/": HOME_WITHOUT_SIGNAL, "/careers": CAREERS_PAGE})

    inspection = build_service(site).inspect(create_startup())

    assert inspection.has_hiring_signal is True
    assert inspection.hiring_signal_method == HiringSignalMethod.PATH_PROBE
    assert inspection.hiring_signal_url == "https://acme.com/careers"
    assert hiring_requests(site) == ["/robots.txt", "/", "/careers"]


def test_path_redirecting_to_home_is_not_a_signal():
    site = FakeSite({"/": HOME_WITHOUT_SIGNAL}, redirects={"/careers": "/", "/jobs": "/"})

    inspection = build_service(site).inspect(create_startup())

    assert inspection.status == InspectionStatus.DONE
    assert inspection.has_hiring_signal is False
    assert inspection.hiring_signal_url == ""


def test_path_serving_the_same_page_as_home_is_not_a_signal():
    spa_shell = "<html><body><div id='root'></div><p>Open positions soon</p></body></html>"
    site = FakeSite({"/": spa_shell, "/careers": spa_shell, "/jobs": spa_shell})

    inspection = build_service(site).inspect(create_startup())

    assert inspection.has_hiring_signal is False


def test_path_without_hiring_words_is_not_a_signal():
    site = FakeSite({"/": HOME_WITHOUT_SIGNAL, "/jobs": "<html><body>Job queue docs</body></html>"})

    inspection = build_service(site).inspect(create_startup())

    assert inspection.has_hiring_signal is False


def test_site_disallowing_robots_is_blocked_without_requesting_pages():
    site = FakeSite({"/": HOME_WITH_SIGNAL}, robots="User-agent: *\nDisallow: /\n")

    inspection = build_service(site).inspect(create_startup())

    assert inspection.status == InspectionStatus.BLOCKED
    assert site.requested_paths == ["/robots.txt"]


def test_paths_disallowed_by_robots_are_not_probed():
    site = FakeSite(
        {"/": HOME_WITHOUT_SIGNAL, "/careers": CAREERS_PAGE},
        robots="User-agent: *\nDisallow: /careers\n",
    )

    inspection = build_service(site).inspect(create_startup())

    assert "/careers" not in site.requested_paths
    assert inspection.has_hiring_signal is False


def test_missing_robots_txt_allows_inspection():
    site = FakeSite({"/": HOME_WITH_SIGNAL}, robots=None)

    inspection = build_service(site).inspect(create_startup())

    assert inspection.has_hiring_signal is True


def test_unreachable_site_is_marked_failed():
    inspection = build_service(unreachable_site).inspect(create_startup())

    assert inspection.status == InspectionStatus.FAILED
    assert "unreachable" in inspection.error


def test_startup_without_own_domain_is_not_inspected():
    startup = create_startup(website="https://github.com/acme/acme")
    site = FakeSite({"/": HOME_WITH_SIGNAL})

    assert build_service(site).inspect(startup) is None
    assert site.requested_paths == []
    assert not WebsiteInspection.objects.exists()


def test_inspecting_again_updates_the_same_record():
    startup = create_startup()
    build_service(FakeSite({"/": HOME_WITH_SIGNAL})).inspect(startup)

    inspection = build_service(FakeSite({"/": HOME_WITHOUT_SIGNAL})).inspect(startup)

    assert WebsiteInspection.objects.count() == 1
    assert inspection.has_hiring_signal is False
    assert inspection.hiring_signal_method == ""


def test_mark_pending_creates_or_resets_the_inspection():
    startup = create_startup()

    inspection = mark_inspection_pending(startup)

    assert inspection.status == InspectionStatus.PENDING
    assert mark_inspection_pending(startup).pk == inspection.pk


def test_site_living_under_a_path_is_inspected_from_its_website_url():
    site = FakeSite({"/tool": HOME_WITH_SIGNAL})

    inspection = build_service(site).inspect(create_startup(website="https://acme.github.io/tool"))

    assert inspection.has_hiring_signal is True
    assert hiring_requests(site) == ["/robots.txt", "/", "/tool"]


def test_missing_root_without_own_website_path_fails():
    site = FakeSite({})

    inspection = build_service(site).inspect(create_startup(website="https://acme.github.io"))

    assert inspection.status == InspectionStatus.FAILED


def test_home_metrics_are_stored_to_measure_single_page_app_shells():
    site = FakeSite({"/": HOME_WITH_SIGNAL})

    inspection = build_service(site).inspect(create_startup())

    assert inspection.home_link_count == 1
    assert inspection.home_text_length == len("careers")
    assert inspection.home_has_app_root is False


def test_organization_address_on_the_home_is_stored_and_cleared_when_unreadable():
    home = (
        "<html><head><script type='application/ld+json'>"
        '{"@type": "Organization", "address": {"addressLocality": "Porto", '
        '"addressCountry": "PT"}}</script></head><body>Acme</body></html>'
    )
    startup = create_startup()

    inspection = build_service(FakeSite({"/": home})).inspect(startup)
    assert inspection.organization_location == "Porto, PT"

    inspection = build_service(unreachable_site).inspect(startup)
    assert inspection.organization_location == ""


def test_home_metrics_are_cleared_when_the_home_cannot_be_read():
    startup = create_startup()
    build_service(FakeSite({"/": HOME_WITH_SIGNAL})).inspect(startup)

    inspection = build_service(unreachable_site).inspect(startup)

    assert inspection.home_text_length is None
    assert inspection.home_link_count is None
    assert inspection.home_has_app_root is None


HOME_LINKING_TEAM = (
    "<html><body><nav><a href='/team'>Team</a></nav>"
    "<footer><a href='mailto:hello@acme.com'>Contact</a></footer></body></html>"
)
TEAM_PAGE = (
    "<html><body><div><h3>Jane Roe</h3><p>CEO &amp; Co-founder</p>"
    "<a href='https://www.linkedin.com/in/jane-roe-fictional'>in</a></div></body></html>"
)


def contacts_of(startup):
    return {
        (contact.full_name, contact.role, contact.email, contact.profile_url)
        for contact in startup.contacts.all()
    }


def test_contacts_from_home_and_linked_team_page_are_saved_as_candidates():
    startup = create_startup()
    site = FakeSite({"/": HOME_LINKING_TEAM, "/team": TEAM_PAGE})

    inspection = build_service(site).inspect(startup)

    assert contacts_of(startup) == {
        ("", ContactRole.GENERAL, "hello@acme.com", ""),
        ("Jane Roe", ContactRole.CEO, "", "https://www.linkedin.com/in/jane-roe-fictional"),
    }
    jane = startup.contacts.get(full_name="Jane Roe")
    assert jane.status == ContactStatus.CANDIDATE
    assert jane.found_via == ContactFoundVia.WEBSITE
    assert jane.evidence_url == "https://acme.com/team"
    assert inspection.contacts_found == 2
    assert "/about" not in site.requested_paths


def test_typical_contact_paths_are_tried_when_home_links_none():
    startup = create_startup()
    site = FakeSite({"/": HOME_WITHOUT_SIGNAL, "/about": TEAM_PAGE})

    build_service(site).inspect(startup)

    assert ("Jane Roe", ContactRole.CEO, "", "https://www.linkedin.com/in/jane-roe-fictional") in (
        contacts_of(startup)
    )
    assert "/contacto" in site.requested_paths


def test_contact_pages_disallowed_by_robots_are_not_visited():
    startup = create_startup()
    site = FakeSite(
        {"/": HOME_LINKING_TEAM, "/team": TEAM_PAGE}, robots="User-agent: *\nDisallow: /team\n"
    )

    build_service(site).inspect(startup)

    assert "/team" not in site.requested_paths
    assert contacts_of(startup) == {("", ContactRole.GENERAL, "hello@acme.com", "")}


def test_inspecting_again_does_not_duplicate_or_reset_reviewed_contacts():
    startup = create_startup()
    site = FakeSite({"/": HOME_LINKING_TEAM, "/team": TEAM_PAGE})
    build_service(site).inspect(startup)
    startup.contacts.filter(full_name="Jane Roe").update(status=ContactStatus.CONFIRMED)

    build_service(site).inspect(startup)

    assert startup.contacts.count() == 2
    assert startup.contacts.get(full_name="Jane Roe").status == ContactStatus.CONFIRMED


def test_at_most_a_few_contact_pages_are_visited():
    links = "".join(f"<a href='/team-{number}/about'>About {number}</a>" for number in range(20))
    site = FakeSite({"/": f"<html><body>{links}</body></html>"})

    build_service(site).inspect(create_startup())

    visited_contact_pages = [path for path in site.requested_paths if path.endswith("/about")]
    assert len(visited_contact_pages) == CONTACT_MAX_EXTRA_PAGES


def test_openings_are_checked_after_the_inspection_reusing_its_robots_txt():
    startup = create_startup()
    site = FakeSite(
        {"/": HOME_WITH_SIGNAL, "/careers": "<a href='/careers/backend'>Backend Engineer</a>"}
    )
    client = httpx.Client(transport=httpx.MockTransport(site), follow_redirects=True)

    inspection = WebsiteInspectionService(http_client=client).inspect(startup)

    assert inspection.openings_status == OpeningsStatus.ACTIVE
    assert startup.job_openings.get().title == "Backend Engineer"
    assert site.requested_paths.count("/robots.txt") == 1
