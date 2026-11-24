from datetime import UTC, datetime

import httpx
import pytest

from startups.constants import JobBoardProvider, OpeningOrigin
from startups.exceptions import JobBoardError
from startups.job_boards import JobBoardClient
from startups.job_listing import JobBoard

ASHBY_RESPONSE = {
    "jobs": [
        {
            "title": "AI Engineer ",
            "location": "Remote",
            "isRemote": True,
            "jobUrl": "https://jobs.ashbyhq.com/acme/1",
            "publishedAt": "2026-10-07T16:24:59.247+00:00",
            "isListed": True,
        },
        {
            "title": "Hidden role",
            "location": "Berlin",
            "isRemote": False,
            "jobUrl": "https://jobs.ashbyhq.com/acme/2",
            "publishedAt": "2026-10-07T16:24:59.247+00:00",
            "isListed": False,
        },
    ]
}
GREENHOUSE_RESPONSE = {
    "jobs": [
        {
            "title": "Accounting Operations Manager",
            "location": {"name": "Distributed (US + Canada)"},
            "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/1",
            "updated_at": "2026-11-18T14:49:00-05:00",
            "first_published": "2026-09-23T18:19:40-04:00",
        }
    ]
}
LEVER_RESPONSE = [
    {
        "text": "Backend Engineer",
        "categories": {"location": "Remote - Europe"},
        "workplaceType": "remote",
        "hostedUrl": "https://jobs.lever.co/acme/1",
        "createdAt": 1793635200000,
    },
    {
        "text": "Apply to be considered for future opportunities",
        "categories": {"location": "Remote"},
        "workplaceType": "remote",
        "hostedUrl": "https://jobs.lever.co/acme/2",
        "createdAt": 1793635200000,
    },
]


class FakeJobBoardApis:
    """Answers each API URL with a fixed JSON body; unknown URLs are 404."""

    def __init__(self, responses):
        self.responses = responses
        self.requested_urls = []

    def __call__(self, request):
        url = str(request.url).split("?")[0]
        self.requested_urls.append(url)
        if url in self.responses:
            return httpx.Response(200, json=self.responses[url])
        return httpx.Response(404)


def build_client(responses):
    apis = FakeJobBoardApis(responses)
    return JobBoardClient(http_client=httpx.Client(transport=httpx.MockTransport(apis))), apis


def test_ashby_listed_openings_with_their_publication_date():
    client, _ = build_client({"https://api.ashbyhq.com/posting-api/job-board/acme": ASHBY_RESPONSE})

    [opening] = client.fetch_openings(JobBoard(JobBoardProvider.ASHBY, "acme"))

    assert opening.title == "AI Engineer"
    assert opening.is_remote is True
    assert opening.published_at == datetime(2026, 10, 7, 16, 24, 59, 247000, tzinfo=UTC)
    assert opening.origin == OpeningOrigin.ASHBY


def test_greenhouse_uses_first_published_and_detects_remote_from_location():
    client, _ = build_client(
        {"https://boards-api.greenhouse.io/v1/boards/acme/jobs": GREENHOUSE_RESPONSE}
    )

    [opening] = client.fetch_openings(JobBoard(JobBoardProvider.GREENHOUSE, "acme"))

    assert opening.published_at.date().isoformat() == "2026-09-23"
    assert opening.location == "Distributed (US + Canada)"
    assert opening.is_remote is None
    assert opening.origin == OpeningOrigin.GREENHOUSE


def test_lever_skips_generic_applications_and_falls_back_to_the_eu_host():
    client, apis = build_client({"https://api.eu.lever.co/v0/postings/acme": LEVER_RESPONSE})

    [opening] = client.fetch_openings(JobBoard(JobBoardProvider.LEVER, "acme"))

    assert opening.title == "Backend Engineer"
    assert opening.is_remote is True
    assert opening.published_at == datetime(2026, 11, 2, 16, 0, tzinfo=UTC)
    assert apis.requested_urls == [
        "https://api.lever.co/v0/postings/acme",
        "https://api.eu.lever.co/v0/postings/acme",
    ]


def test_unknown_board_raises_job_board_error():
    client, _ = build_client({})

    with pytest.raises(JobBoardError):
        client.fetch_openings(JobBoard(JobBoardProvider.ASHBY, "missing"))


def test_ashby_and_lever_give_the_country_of_each_opening():
    ashby_job = {
        **ASHBY_RESPONSE["jobs"][0],
        "address": {"postalAddress": {"addressCountry": "United Kingdom"}},
    }
    lever_posting = {**LEVER_RESPONSE[0], "country": "DE"}
    client, _ = build_client(
        {
            "https://api.ashbyhq.com/posting-api/job-board/acme": {"jobs": [ashby_job]},
            "https://api.lever.co/v0/postings/acme": [lever_posting],
        }
    )

    [ashby_opening] = client.fetch_openings(JobBoard(JobBoardProvider.ASHBY, "acme"))
    [lever_opening] = client.fetch_openings(JobBoard(JobBoardProvider.LEVER, "acme"))

    assert ashby_opening.country_hint == "United Kingdom"
    assert lever_opening.country_hint == "DE"


def test_greenhouse_headquarters_is_the_office_named_so():
    client, _ = build_client(
        {
            "https://boards-api.greenhouse.io/v1/boards/acme/offices": {
                "offices": [
                    {"name": "Any location", "location": None},
                    {"name": "Headquarters", "location": "Santa Clara, California, United States"},
                ]
            }
        }
    )

    headquarters = client.fetch_headquarters(JobBoard(JobBoardProvider.GREENHOUSE, "acme"))

    assert headquarters == "Santa Clara, California, United States"


def test_headquarters_is_blank_for_other_boards_or_without_such_office():
    client, apis = build_client(
        {"https://boards-api.greenhouse.io/v1/boards/acme/offices": {"offices": []}}
    )

    assert client.fetch_headquarters(JobBoard(JobBoardProvider.GREENHOUSE, "acme")) == ""
    assert client.fetch_headquarters(JobBoard(JobBoardProvider.ASHBY, "acme")) == ""
    assert apis.requested_urls == ["https://boards-api.greenhouse.io/v1/boards/acme/offices"]
