from datetime import timedelta

import httpx
import pytest
from django.utils import timezone

from sources.constants import SourceKey
from sources.models import Source, SourceRecord
from startups.constants import (
    OPENINGS_MAX_AGE_DAYS,
    InspectionStatus,
    LocationSource,
    OpeningOrigin,
    OpeningsStatus,
)
from startups.models import JobOpening, Startup, StartupDomain, WebsiteInspection
from startups.openings import OpeningsVerifier

pytestmark = pytest.mark.django_db

CAREERS_URL = "https://acme.com/careers"
ASHBY_API_URL = "https://api.ashbyhq.com/posting-api/job-board/acme"
GREENHOUSE_API_URL = "https://boards-api.greenhouse.io/v1/boards/acme/jobs"
ASHBY_CAREERS_PAGE = (
    "<html><body><script src='https://jobs.ashbyhq.com/acme/embed'></script></body></html>"
)
LISTING_PAGE = (
    "<html><body><a href='/careers/backend-engineer'>Backend Engineer · Remote</a></body></html>"
)
NO_OPENINGS_PAGE = "<html><body><p>There are no open positions right now.</p></body></html>"
EMPTY_SHELL = "<html><body><div id='root'></div></body></html>"
ALLOW_ALL_ROBOTS = "User-agent: *\nAllow: /\n"


def iso_days_ago(days):
    return (timezone.now() - timedelta(days=days)).isoformat()


def ashby_jobs(*days_ago):
    return {
        "jobs": [
            {
                "title": f"Engineer {position}",
                "location": "Remote",
                "isRemote": True,
                "jobUrl": f"https://jobs.ashbyhq.com/acme/{position}",
                "publishedAt": iso_days_ago(days),
                "isListed": True,
            }
            for position, days in enumerate(days_ago)
        ]
    }


class FakeInternet:
    """Serves pages and API answers by URL (without query) and records what was requested."""

    def __init__(self, pages=None, api_responses=None, robots=ALLOW_ALL_ROBOTS):
        self.pages = pages or {}
        self.api_responses = api_responses or {}
        self.robots = robots
        self.redirect_bodies = {}
        self.requested_urls = []

    def __call__(self, request):
        url = str(request.url).split("?")[0]
        self.requested_urls.append(url)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=self.robots)
        if url in self.redirect_bodies:
            return httpx.Response(
                307, text=self.redirect_bodies[url], headers={"Content-Type": "text/html"}
            )
        if url in self.api_responses:
            return httpx.Response(200, json=self.api_responses[url])
        if url in self.pages:
            return httpx.Response(
                200, text=self.pages[url], headers={"Content-Type": "text/html; charset=utf-8"}
            )
        return httpx.Response(404)


def build_verifier(internet):
    client = httpx.Client(transport=httpx.MockTransport(internet), follow_redirects=True)
    return OpeningsVerifier(http_client=client)


def create_startup(signal_url=CAREERS_URL):
    startup = Startup.objects.create(name="Acme", website="https://acme.com")
    StartupDomain.objects.create(startup=startup, domain="acme.com", is_primary=True)
    WebsiteInspection.objects.create(
        startup=startup,
        status=InspectionStatus.DONE,
        has_hiring_signal=bool(signal_url),
        hiring_signal_url=signal_url,
    )
    return startup


def add_hiring_post(startup, comment_html):
    SourceRecord.objects.create(
        source=Source.objects.get(key=SourceKey.HACKER_NEWS_HIRING),
        startup=startup,
        external_id=f"post-{startup.pk}",
        payload={"comment_text": comment_html},
    )


def test_job_board_embedded_in_the_careers_page_is_read_through_its_api():
    startup = create_startup()
    internet = FakeInternet(
        pages={CAREERS_URL: ASHBY_CAREERS_PAGE}, api_responses={ASHBY_API_URL: ashby_jobs(3, 10)}
    )

    inspection = build_verifier(internet).verify(startup)

    assert inspection.openings_status == OpeningsStatus.ACTIVE
    assert inspection.openings_checked_at is not None
    assert startup.job_openings.count() == 2
    assert set(startup.job_openings.values_list("origin", flat=True)) == {OpeningOrigin.ASHBY}


def test_board_openings_older_than_the_limit_are_not_active():
    startup = create_startup()
    internet = FakeInternet(
        pages={CAREERS_URL: ASHBY_CAREERS_PAGE},
        api_responses={ASHBY_API_URL: ashby_jobs(OPENINGS_MAX_AGE_DAYS + 5)},
    )

    inspection = build_verifier(internet).verify(startup)

    assert inspection.openings_status == OpeningsStatus.NONE
    assert not startup.job_openings.exists()


def test_board_without_openings_means_no_active_openings():
    startup = create_startup()
    internet = FakeInternet(
        pages={CAREERS_URL: ASHBY_CAREERS_PAGE}, api_responses={ASHBY_API_URL: {"jobs": []}}
    )

    assert build_verifier(internet).verify(startup).openings_status == OpeningsStatus.NONE


def test_jobs_listed_on_the_careers_page_count_as_active_without_a_date():
    startup = create_startup()
    internet = FakeInternet(pages={CAREERS_URL: LISTING_PAGE})

    inspection = build_verifier(internet).verify(startup)

    opening = startup.job_openings.get()
    assert inspection.openings_status == OpeningsStatus.ACTIVE
    assert inspection.openings_url == CAREERS_URL
    assert (opening.title, opening.origin, opening.published_at) == (
        "Backend Engineer · Remote",
        OpeningOrigin.WEBSITE,
        None,
    )


def test_careers_page_saying_there_are_no_openings():
    startup = create_startup()
    internet = FakeInternet(pages={CAREERS_URL: NO_OPENINGS_PAGE})

    assert build_verifier(internet).verify(startup).openings_status == OpeningsStatus.NONE


def test_careers_page_that_shows_nothing_readable_is_unverified():
    startup = create_startup()
    internet = FakeInternet(pages={CAREERS_URL: EMPTY_SHELL})

    assert build_verifier(internet).verify(startup).openings_status == OpeningsStatus.UNVERIFIED


def test_careers_page_disallowed_by_robots_is_not_read():
    startup = create_startup()
    internet = FakeInternet(
        pages={CAREERS_URL: LISTING_PAGE}, robots="User-agent: *\nDisallow: /careers\n"
    )

    inspection = build_verifier(internet).verify(startup)

    assert inspection.openings_status == OpeningsStatus.UNVERIFIED
    assert CAREERS_URL not in internet.requested_urls


def test_failing_board_api_falls_back_to_the_page():
    startup = create_startup()
    page_with_board_and_listing = ASHBY_CAREERS_PAGE.replace(
        "</body>", "<a href='/careers/designer'>Product Designer</a></body>"
    )
    internet = FakeInternet(pages={CAREERS_URL: page_with_board_and_listing})

    inspection = build_verifier(internet).verify(startup)

    assert inspection.openings_status == OpeningsStatus.ACTIVE
    assert startup.job_openings.get().title == "Product Designer"


def test_job_board_linked_from_a_who_is_hiring_post_is_used_without_website_signal():
    startup = create_startup(signal_url="")
    add_hiring_post(
        startup,
        "Acme | Backend Engineer | REMOTE<p>Apply: "
        '<a href="https:&#x2F;&#x2F;job-boards.greenhouse.io&#x2F;acme">jobs</a>',
    )
    greenhouse_jobs = {
        "jobs": [
            {
                "title": "Backend Engineer",
                "location": {"name": "Remote"},
                "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/1",
                "first_published": iso_days_ago(5),
            }
        ]
    }
    internet = FakeInternet(api_responses={GREENHOUSE_API_URL: greenhouse_jobs})

    inspection = build_verifier(internet).verify(startup)

    assert inspection.openings_status == OpeningsStatus.ACTIVE
    assert inspection.openings_url == "https://job-boards.greenhouse.io/acme"
    assert startup.job_openings.get().is_remote is True


def test_startup_without_signal_or_board_is_not_checked():
    startup = create_startup(signal_url="")
    internet = FakeInternet()

    inspection = build_verifier(internet).verify(startup)

    assert inspection.openings_status == OpeningsStatus.NOT_CHECKED
    assert internet.requested_urls == []


def test_verifying_again_replaces_the_openings():
    startup = create_startup()
    JobOpening.objects.create(startup=startup, title="Closed role", origin=OpeningOrigin.WEBSITE)
    internet = FakeInternet(pages={CAREERS_URL: LISTING_PAGE})

    build_verifier(internet).verify(startup)

    assert list(startup.job_openings.values_list("title", flat=True)) == [
        "Backend Engineer · Remote"
    ]


def test_signal_pointing_straight_to_a_job_board_uses_its_api():
    startup = create_startup(signal_url="https://jobs.ashbyhq.com/acme")
    internet = FakeInternet(api_responses={ASHBY_API_URL: ashby_jobs(1)})

    inspection = build_verifier(internet).verify(startup)

    assert inspection.openings_status == OpeningsStatus.ACTIVE
    assert "https://jobs.ashbyhq.com/acme" not in internet.requested_urls


@pytest.mark.parametrize(
    "signal_url",
    [
        "mailto:jobs@acme.com",
        "https://acme.com/cdn-cgi/l/email-protection#0a62634a",
        "https://itch.io/jobs",
    ],
)
def test_signal_that_is_not_a_careers_page_of_the_startup_stays_unverified(signal_url):
    startup = create_startup(signal_url=signal_url)
    internet = FakeInternet()

    inspection = build_verifier(internet).verify(startup)

    assert inspection.openings_status == OpeningsStatus.UNVERIFIED
    assert internet.requested_urls == []


def test_redirect_answer_naming_a_job_board_uses_the_board():
    startup = create_startup()
    internet = FakeInternet(api_responses={ASHBY_API_URL: ashby_jobs(2)})
    internet.redirect_bodies = {CAREERS_URL: "<a href='https://jobs.ashbyhq.com/acme'>Moved</a>"}

    inspection = build_verifier(internet).verify(startup)

    assert inspection.openings_status == OpeningsStatus.ACTIVE


def test_open_positions_link_is_followed_one_step():
    startup = create_startup()
    internet = FakeInternet(
        pages={
            CAREERS_URL: "<a href='/careers/open-roles'>See open positions</a>",
            "https://acme.com/careers/open-roles": LISTING_PAGE,
        }
    )

    inspection = build_verifier(internet).verify(startup)

    assert inspection.openings_status == OpeningsStatus.ACTIVE
    assert inspection.openings_url == "https://acme.com/careers/open-roles"


def test_each_opening_gets_the_place_closest_to_madrid_of_those_it_names():
    startup = create_startup()
    jobs = ashby_jobs(1, 2, 3)
    jobs["jobs"][0]["location"] = "New York, San Francisco or London"
    jobs["jobs"][1]["location"] = "Remote"
    jobs["jobs"][1]["address"] = {"postalAddress": {"addressCountry": "Germany"}}
    jobs["jobs"][2]["location"] = "Remote"
    internet = FakeInternet(
        pages={CAREERS_URL: ASHBY_CAREERS_PAGE}, api_responses={ASHBY_API_URL: jobs}
    )

    build_verifier(internet).verify(startup)

    places = {
        title: (country, timezone_name)
        for title, country, timezone_name in startup.job_openings.values_list(
            "title", "country", "timezone_name"
        )
    }
    assert places == {
        "Engineer 0": ("GB", "Europe/London"),
        "Engineer 1": ("DE", "Europe/Berlin"),
        "Engineer 2": ("", ""),
    }


def test_greenhouse_headquarters_is_kept_and_the_location_detected():
    startup = create_startup(signal_url="https://job-boards.greenhouse.io/acme")
    internet = FakeInternet(
        api_responses={
            GREENHOUSE_API_URL: {
                "jobs": [
                    {
                        "title": "Backend Engineer",
                        "location": {"name": "Remote"},
                        "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/1",
                        "first_published": iso_days_ago(2),
                    }
                ]
            },
            "https://boards-api.greenhouse.io/v1/boards/acme/offices": {
                "offices": [{"name": "Headquarters", "location": "Lisbon, Portugal"}]
            },
        }
    )

    inspection = build_verifier(internet).verify(startup)

    startup.refresh_from_db()
    assert inspection.headquarters_location == "Lisbon, Portugal"
    assert startup.hq_country == "PT"
    assert startup.location_source == LocationSource.HEADQUARTERS
