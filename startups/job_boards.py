"""Reads a company's openings from the official public APIs of Ashby, Greenhouse and Lever.

The three are documented, free and need no key for reading published jobs:
- Ashby: https://developers.ashbyhq.com/docs/public-job-posting-api
- Greenhouse: https://developers.greenhouse.io/job-board.html
- Lever: https://github.com/lever/postings-api
Each returns the exact list of published jobs with their publication date.
"""

from datetime import UTC, datetime

import httpx

from startups.constants import (
    ASHBY_API_URL,
    GREENHOUSE_API_PARAMS,
    GREENHOUSE_API_URL,
    GREENHOUSE_OFFICES_API_URL,
    HTTP_NOT_FOUND,
    JOB_DESCRIPTION_MAX_LENGTH,
    JOB_LOCATION_MAX_LENGTH,
    JOB_TITLE_MAX_LENGTH,
    LEVER_API_PARAMS,
    LEVER_API_URLS,
    LEVER_DESCRIPTION_FIELDS,
    LEVER_ONSITE_WORKPLACES,
    LEVER_REMOTE_WORKPLACE,
    MILLISECONDS_PER_SECOND,
    JobBoardProvider,
    OpeningOrigin,
)
from startups.exceptions import JobBoardError
from startups.job_listing import (
    OpeningCandidate,
    is_generic_application,
    is_remote_text,
    parse_publication_date,
)
from startups.locations import names_headquarters


class JobBoardClient:
    def __init__(self, http_client):
        self.http_client = http_client

    def fetch_openings(self, board):
        """The board's published openings, without generic applications.

        Raises `JobBoardError` if the board does not exist or the API cannot be read.
        """
        readers = {
            JobBoardProvider.ASHBY: self._ashby_openings,
            JobBoardProvider.GREENHOUSE: self._greenhouse_openings,
            JobBoardProvider.LEVER: self._lever_openings,
        }
        openings = readers[board.provider](board.slug)
        return [opening for opening in openings if not is_generic_application(opening.title)]

    def fetch_headquarters(self, board):
        """The location of the office the board calls headquarters, or blank.

        Only Greenhouse lists offices; a board that cannot be read gives blank too.
        """
        if board.provider != JobBoardProvider.GREENHOUSE:
            return ""
        try:
            body = self._get_json(GREENHOUSE_OFFICES_API_URL.format(slug=board.slug))
        except JobBoardError:
            return ""
        for office in body.get("offices") or []:
            if names_headquarters(office.get("name")) and office.get("location"):
                return _clean(office["location"], JOB_LOCATION_MAX_LENGTH)
        return ""

    def _ashby_openings(self, slug):
        body = self._get_json(ASHBY_API_URL.format(slug=slug))
        return [
            OpeningCandidate(
                title=_clean(job.get("title"), JOB_TITLE_MAX_LENGTH),
                location=_clean(job.get("location"), JOB_LOCATION_MAX_LENGTH),
                is_remote=job.get("isRemote") if isinstance(job.get("isRemote"), bool) else None,
                url=job.get("jobUrl") or "",
                published_at=parse_publication_date(job.get("publishedAt")),
                origin=OpeningOrigin.ASHBY,
                country_hint=_ashby_country(job),
                description=_description(job.get("descriptionPlain")),
            )
            for job in body.get("jobs", [])
            if job.get("isListed", True)
        ]

    def _greenhouse_openings(self, slug):
        body = self._get_json(GREENHOUSE_API_URL.format(slug=slug), params=GREENHOUSE_API_PARAMS)
        openings = []
        for job in body.get("jobs", []):
            location = (job.get("location") or {}).get("name") or ""
            openings.append(
                OpeningCandidate(
                    title=_clean(job.get("title"), JOB_TITLE_MAX_LENGTH),
                    location=_clean(location, JOB_LOCATION_MAX_LENGTH),
                    is_remote=is_remote_text(location),
                    url=job.get("absolute_url") or "",
                    published_at=parse_publication_date(
                        job.get("first_published") or job.get("updated_at")
                    ),
                    origin=OpeningOrigin.GREENHOUSE,
                    description=_description(job.get("content")),
                )
            )
        return openings

    def _lever_openings(self, slug):
        body = None
        for api_url in LEVER_API_URLS:
            try:
                body = self._get_json(api_url.format(slug=slug), params=LEVER_API_PARAMS)
                break
            except JobBoardError:
                continue
        if body is None:
            raise JobBoardError(f"Lever board '{slug}' not found")
        return [
            OpeningCandidate(
                title=_clean(posting.get("text"), JOB_TITLE_MAX_LENGTH),
                location=_clean(
                    (posting.get("categories") or {}).get("location"), JOB_LOCATION_MAX_LENGTH
                ),
                is_remote=_lever_is_remote(posting),
                url=posting.get("hostedUrl") or "",
                published_at=_from_milliseconds(posting.get("createdAt")),
                origin=OpeningOrigin.LEVER,
                country_hint=str(posting.get("country") or ""),
                description=_lever_description(posting),
            )
            for posting in body
        ]

    def _get_json(self, url, params=None):
        try:
            response = self.http_client.get(url, params=params)
        except httpx.HTTPError as error:
            raise JobBoardError(f"{url}: {error}") from error
        if response.status_code == HTTP_NOT_FOUND or response.is_error:
            raise JobBoardError(f"{url}: HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as error:
            raise JobBoardError(f"{url}: not JSON") from error


def _lever_description(posting):
    """Its description, its lists ("Requirements") and its closing text, as one text."""
    parts = [str(posting.get(field) or "") for field in LEVER_DESCRIPTION_FIELDS]
    for job_list in posting.get("lists") or []:
        if isinstance(job_list, dict):
            parts.append(f"{job_list.get('text') or ''}\n{job_list.get('content') or ''}")
    return _description("\n".join(part for part in parts if part))


def _description(value):
    return str(value or "")[:JOB_DESCRIPTION_MAX_LENGTH]


def _ashby_country(job):
    postal_address = (job.get("address") or {}).get("postalAddress") or {}
    return str(postal_address.get("addressCountry") or "")


def _lever_is_remote(posting):
    workplace = str(posting.get("workplaceType") or "").lower()
    if workplace == LEVER_REMOTE_WORKPLACE:
        return True
    if workplace in LEVER_ONSITE_WORKPLACES:
        return False
    return is_remote_text((posting.get("categories") or {}).get("location"))


def _from_milliseconds(value):
    if not isinstance(value, int | float):
        return None
    return datetime.fromtimestamp(value / MILLISECONDS_PER_SECOND, tz=UTC)


def _clean(value, max_length):
    return " ".join(str(value or "").split())[:max_length]
