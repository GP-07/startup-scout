import httpx
import pytest

from sources.constants import SourceKey
from sources.models import Source
from startups.constants import HiringSignalKind, HiringSignalMethod, InspectionStatus
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


def unreachable_site(request):
    raise httpx.ConnectError("unreachable", request=request)


def build_service(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return WebsiteInspectionService(http_client=client)


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
    assert site.requested_paths == ["/robots.txt", "/"]


def test_falls_back_to_typical_paths_when_home_has_no_signal():
    site = FakeSite({"/": HOME_WITHOUT_SIGNAL, "/careers": CAREERS_PAGE})

    inspection = build_service(site).inspect(create_startup())

    assert inspection.has_hiring_signal is True
    assert inspection.hiring_signal_method == HiringSignalMethod.PATH_PROBE
    assert inspection.hiring_signal_url == "https://acme.com/careers"
    assert site.requested_paths == ["/robots.txt", "/", "/careers"]


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
    assert site.requested_paths == ["/robots.txt", "/", "/tool"]


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


def test_home_metrics_are_cleared_when_the_home_cannot_be_read():
    startup = create_startup()
    build_service(FakeSite({"/": HOME_WITH_SIGNAL})).inspect(startup)

    inspection = build_service(unreachable_site).inspect(startup)

    assert inspection.home_text_length is None
    assert inspection.home_link_count is None
    assert inspection.home_has_app_root is None
