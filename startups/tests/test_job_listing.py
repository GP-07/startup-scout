import json
from datetime import UTC, datetime

import pytest

from startups.constants import JobBoardProvider, OpeningOrigin
from startups.job_listing import (
    JobBoard,
    extract_openings,
    find_job_board,
    is_generic_application,
    open_positions_links,
    says_no_openings,
)

CAREERS_URL = "https://www.acme.com/careers"


def page(body, head=""):
    return f"<html><head><title>Careers</title>{head}</head><body>{body}</body></html>"


def titles(openings):
    return [opening.title for opening in openings]


def test_listed_job_links_below_the_careers_page_are_openings():
    html = page(
        "<nav><a href='/careers'>Careers</a><a href='/blog/hiring-tips'>Hiring tips</a></nav>"
        "<a href='/careers/backend-engineer'>"
        "<h3>Backend Engineer</h3><span>Remote · Full-time</span></a>"
        "<a href='/careers/product-designer'><h3>Product Designer</h3><span>Barcelona</span></a>"
        "<a href='/careers/benefits'>Our benefits</a>"
    )

    openings = extract_openings(html, CAREERS_URL)

    assert titles(openings) == ["Backend Engineer", "Product Designer"]
    backend = openings[0]
    assert backend.url == "https://www.acme.com/careers/backend-engineer"
    assert backend.is_remote is True
    assert backend.published_at is None
    assert backend.origin == OpeningOrigin.WEBSITE
    assert openings[1].is_remote is None


def test_links_to_job_pages_on_a_job_board_are_openings():
    html = page(
        "<a href='https://jobs.ashbyhq.com/acme/1234-abcd'>Founding Engineer</a>"
        "<a href='https://jobs.ashbyhq.com/acme'>All jobs</a>"
    )

    assert titles(extract_openings(html, CAREERS_URL)) == ["Founding Engineer"]


def test_json_ld_job_postings_give_title_date_and_remote():
    posting = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Data Engineer",
        "datePosted": "2026-11-02",
        "jobLocationType": "TELECOMMUTE",
        "url": "https://www.acme.com/careers/data-engineer",
    }
    html = page(
        "<p>Join us</p>", head=f"<script type='application/ld+json'>{json.dumps(posting)}</script>"
    )

    [opening] = extract_openings(html, CAREERS_URL)

    assert opening.title == "Data Engineer"
    assert opening.published_at == datetime(2026, 11, 2, tzinfo=UTC)
    assert opening.is_remote is True


def test_generic_applications_are_not_openings():
    html = page(
        "<a href='/careers/general-application'>General Application</a>"
        "<a href='/careers/talent-pool'>Talent pool: apply for future opportunities</a>"
    )

    assert extract_openings(html, CAREERS_URL) == []


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Open Application", True),
        ("Don't see your role? Apply here", True),
        ("Spontaneous application", True),
        ("Candidatura espontánea", True),
        ("Senior Backend Engineer", False),
    ],
)
def test_is_generic_application(title, expected):
    assert is_generic_application(title) is expected


@pytest.mark.parametrize(
    "text",
    [
        "There are no open positions at the moment.",
        "We're not hiring right now, but check back soon!",
        "No current openings",
        "Ahora mismo no hay búsquedas abiertas",
    ],
)
def test_pages_saying_there_are_no_openings(text):
    assert says_no_openings(page(f"<p>{text}</p>")) is True


def test_a_page_with_openings_does_not_say_there_are_none():
    assert says_no_openings(page("<p>We have open positions!</p>")) is False


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        (
            "<script src='https://jobs.ashbyhq.com/Mastra/embed?version=2'></script>",
            JobBoard(JobBoardProvider.ASHBY, "Mastra"),
        ),
        (
            "<a href='https://job-boards.greenhouse.io/hatchcareers/jobs/4683890006'>Job</a>",
            JobBoard(JobBoardProvider.GREENHOUSE, "hatchcareers"),
        ),
        (
            "<script src='https://boards.greenhouse.io/embed/job_board/js?for=acme'></script>",
            JobBoard(JobBoardProvider.GREENHOUSE, "acme"),
        ),
        (
            "<iframe src='https://jobs.lever.co/distru'></iframe>",
            JobBoard(JobBoardProvider.LEVER, "distru"),
        ),
        (
            "<a href='https://jobs.eu.lever.co/acme/abc'>Job</a>",
            JobBoard(JobBoardProvider.LEVER, "acme"),
        ),
        ("<a href='https://acme.com/jobs'>Jobs</a>", None),
    ],
)
def test_find_job_board(html, expected):
    assert find_job_board(html) == expected


def test_on_a_job_platform_only_jobs_below_the_company_page_count():
    company_jobs_url = "https://wellfound.com/company/acme/jobs"
    html = page(
        "<a href='/company/acme/jobs/123-backend-engineer'>Backend Engineer</a>"
        "<a href='/role/financial-analyst'>Financial Analyst Jobs</a>"
    )

    assert titles(extract_openings(html, company_jobs_url)) == ["Backend Engineer"]


def test_open_positions_links_point_to_where_the_jobs_are():
    html = page(
        "<a href='/careers#benefits'>Benefits</a>"
        "<a href='/careers/open-roles'>See open positions</a>"
        "<a href='https://other-fictional.com/jobs'>Open roles at our partner</a>"
    )

    assert open_positions_links(html, CAREERS_URL) == ["https://www.acme.com/careers/open-roles"]


def test_json_ld_job_posting_gives_its_country():
    page = (
        "<script type='application/ld+json'>"
        '{"@type": "JobPosting", "title": "Backend Engineer", "jobLocation": {"address": '
        '{"addressLocality": "Lyon", "addressCountry": {"@type": "Country", "name": "FR"}}}}'
        "</script>"
    )

    [opening] = extract_openings(page, "https://acme.com/careers")

    assert opening.location == "Lyon"
    assert opening.country_hint == "FR"
