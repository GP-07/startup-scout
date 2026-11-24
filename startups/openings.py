"""Checks whether a startup's openings are actually published today.

A hiring signal (a careers link) says a startup has a place for openings, not that it has any.
This visits the signal's target and settles it (docs/startup-scout-design.md §3):

1. If the page or link belongs to Ashby, Greenhouse or Lever, their official API lists the
   published jobs with their dates. Only those published in the last OPENINGS_MAX_AGE_DAYS
   count; an answer without any means there are no active openings.
2. Otherwise the careers page itself: the jobs it lists (always active, as they rarely carry a
   date), or a statement such as "No open positions".
3. If nothing can be told, the openings stay unverified.

Job boards linked from a "Who is hiring?" post are checked too, even without a website signal:
the post is a lead, the board is the proof.
"""

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import urlsplit

import httpx
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from sources.constants import SourceKey
from startups.constants import (
    EMAIL_PROTECTION_PATH,
    HTTP_OK,
    INSPECTION_TIMEOUT_SECONDS,
    INSPECTION_USER_AGENT,
    JOB_SECTION_DOMAINS,
    OPEN_POSITIONS_LINKS_FOLLOWED,
    OPENINGS_MAX_AGE_DAYS,
    OPENINGS_RECHECK_DAYS,
    ROBOTS_USER_AGENT_TOKEN,
    WEB_URL_SCHEMES,
    OpeningsStatus,
    StartupStatus,
)
from startups.domains import normalize_domain
from startups.exceptions import InvalidWebsiteError, JobBoardError
from startups.headquarters import detect_location
from startups.job_boards import JobBoardClient
from startups.job_listing import (
    extract_openings,
    find_job_board,
    open_positions_links,
    says_no_openings,
)
from startups.locations import closest_place, country_place, resolve_places
from startups.models import JobOpening, Startup, WebsiteInspection
from startups.web_pages import html_of, load_robots, site_root

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OpeningsCheck:
    status: str
    url: str = ""
    openings: list = field(default_factory=list)
    # The location of the office the job board calls headquarters, if it says.
    headquarters: str = ""


class OpeningsVerifier:
    def __init__(self, http_client=None):
        self._http_client = http_client
        self._robots_by_site = {}

    @property
    def http_client(self):
        if self._http_client is None:
            self._http_client = httpx.Client(
                follow_redirects=True,
                timeout=INSPECTION_TIMEOUT_SECONDS,
                headers={"User-Agent": INSPECTION_USER_AGENT},
            )
        return self._http_client

    def verify(self, startup, known_robots=None):
        """Check the startup's openings, replace its `JobOpening`s and return the inspection.

        Then detects again where the startup is established: its openings are evidence.
        `known_robots` maps a site root to its already parsed robots.txt, to avoid reading it
        again right after the website inspection.
        """
        self._robots_by_site = dict(known_robots or {})
        inspection, _ = WebsiteInspection.objects.get_or_create(startup=startup)
        inspection = self._save(inspection, *self._settle(startup, inspection))
        detect_location(startup)
        return inspection

    def _settle(self, startup, inspection):
        """(check, whether it was checked) for the startup's targets."""
        targets = _targets(startup, inspection)
        if targets:
            return self._check(targets), True
        if inspection.has_hiring_signal:
            # A signal with no careers page of its own to read (a jobs@ email, another site).
            return OpeningsCheck(OpeningsStatus.UNVERIFIED, url=_web_url_or_blank(inspection)), True
        return OpeningsCheck(OpeningsStatus.NOT_CHECKED), False

    def _check(self, targets):
        unverified_url = targets[0]
        for target_url in targets:
            board = find_job_board(target_url)
            if board is not None:
                check = self._check_board(board, board.public_url)
                if check is not None:
                    return check
                continue
            page = self._read_page(target_url)
            if page is None:
                continue
            page_url, page_html, is_ok = page
            if not is_ok:
                # Some sites answer a redirect without `Location`, naming their job board.
                board = find_job_board(page_html)
                check = self._check_board(board, page_url) if board else None
                if check is not None:
                    return check
                continue
            check = self._check_page(page_url, page_html, follow_links=True)
            if check.status != OpeningsStatus.UNVERIFIED:
                return check
            unverified_url = page_url
        return OpeningsCheck(OpeningsStatus.UNVERIFIED, url=unverified_url)

    def _check_page(self, page_url, page_html, follow_links):
        """Board, listed jobs or a "no openings" statement on the page.

        With `follow_links`, an undecided page leads one step further through its "See open
        positions" links: many careers pages keep the jobs on another page.
        """
        board = find_job_board(page_html)
        if board is not None:
            check = self._check_board(board, page_url)
            if check is not None:
                return check
        openings = extract_openings(page_html, page_url)
        if openings:
            return _check_from(openings, page_url)
        if says_no_openings(page_html):
            return OpeningsCheck(OpeningsStatus.NONE, url=page_url)
        if follow_links:
            for linked_url in open_positions_links(page_html, page_url)[
                :OPEN_POSITIONS_LINKS_FOLLOWED
            ]:
                linked_page = self._read_page(linked_url)
                if linked_page is None or not linked_page[2]:
                    continue
                check = self._check_page(linked_page[0], linked_page[1], follow_links=False)
                if check.status != OpeningsStatus.UNVERIFIED:
                    return check
        return OpeningsCheck(OpeningsStatus.UNVERIFIED, url=page_url)

    def _check_board(self, board, checked_url):
        """The board's answer, or None if its API could not be read (the caller falls back)."""
        board_client = JobBoardClient(self.http_client)
        try:
            openings = board_client.fetch_openings(board)
        except JobBoardError as error:
            logger.info("Could not read job board %s: %s", board, error)
            return None
        return _check_from(
            openings, checked_url, headquarters=board_client.fetch_headquarters(board)
        )

    def _read_page(self, url):
        """(final URL, HTML, answered OK) of a page robots.txt allows, or None."""
        try:
            robots = self._robots_for(url)
            if not robots.can_fetch(ROBOTS_USER_AGENT_TOKEN, url):
                return None
            response = self.http_client.get(url)
        except httpx.HTTPError as error:
            logger.info("Could not read careers page %s: %s", url, error)
            return None
        page_html = html_of(response)
        if not page_html:
            return None
        return str(response.url), page_html, response.status_code == HTTP_OK

    def _robots_for(self, url):
        root_url = site_root(url)
        if root_url not in self._robots_by_site:
            self._robots_by_site[root_url] = load_robots(self.http_client, url)
        return self._robots_by_site[root_url]

    @transaction.atomic
    def _save(self, inspection, check, checked):
        inspection.startup.job_openings.all().delete()
        places = _opening_places(check.openings)
        JobOpening.objects.bulk_create(
            JobOpening(
                startup=inspection.startup,
                title=opening.title,
                location=opening.location,
                is_remote=opening.is_remote,
                url=opening.url,
                published_at=opening.published_at,
                origin=opening.origin,
                country=place.country if place else "",
                timezone_name=place.timezone_name if place else "",
            )
            for opening, place in zip(check.openings, places, strict=True)
        )
        inspection.openings_status = check.status
        inspection.openings_url = check.url
        inspection.openings_checked_at = timezone.now() if checked else None
        inspection.headquarters_location = check.headquarters
        inspection.save(
            update_fields=[
                "openings_status",
                "openings_url",
                "openings_checked_at",
                "headquarters_location",
            ]
        )
        return inspection


def _targets(startup, inspection):
    """Where to look, in order: the website's hiring signal, then boards from job posts."""
    targets = []
    signal_url = _web_url_or_blank(inspection)
    if signal_url and _is_careers_page_of(startup, signal_url):
        targets.append(signal_url)
    hiring_posts = startup.source_records.filter(source__key=SourceKey.HACKER_NEWS_HIRING)
    for payload in hiring_posts.values_list("payload", flat=True):
        board = find_job_board(str((payload or {}).get("comment_text") or ""))
        if board is not None and board.public_url not in targets:
            targets.append(board.public_url)
    return targets


def _web_url_or_blank(inspection):
    """The signal's URL if it is a web page: not a `mailto:` nor an obfuscated email."""
    signal_url = inspection.hiring_signal_url if inspection.has_hiring_signal else ""
    parts = urlsplit(signal_url)
    if parts.scheme not in WEB_URL_SCHEMES or EMAIL_PROTECTION_PATH in parts.path:
        return ""
    return signal_url


def _is_careers_page_of(startup, url):
    """A page of the startup's own domains, its company page on YC or Wellfound, or its board.

    A signal pointing elsewhere (the jobs board of the platform hosting it) says nothing about
    the startup's own openings.
    """
    if find_job_board(url) is not None:
        return True
    try:
        domain = normalize_domain(url)
    except InvalidWebsiteError:
        return False
    if domain in JOB_SECTION_DOMAINS:
        return True
    return startup.domains.filter(domain=domain).exists()


def _opening_places(openings):
    """For each opening, the place closest to Madrid of those it names, or None.

    A city whose name several countries share ("San Carlos") goes to the country most of the
    other openings are in.
    """
    now = timezone.now()
    first_reading = [
        resolve_places(opening.location, country_hint=opening.country_hint) for opening in openings
    ]
    countries = Counter(
        place.country for places in first_reading for place in set(places) if place.country
    )
    preferred_country = _closest_top_country(countries, now)
    return [
        closest_place(
            resolve_places(
                opening.location,
                country_hint=opening.country_hint,
                preferred_country=preferred_country,
            ),
            now,
        )
        for opening in openings
    ]


def _closest_top_country(countries, now):
    """The most frequent country; in a tie, the one closest to Madrid. Blank without any."""
    if not countries:
        return ""
    top_count = max(countries.values())
    tied_places = [
        country_place(country) for country, count in countries.items() if count == top_count
    ]
    place = closest_place([place for place in tied_places if place is not None], now)
    return place.country if place else ""


def _check_from(openings, checked_url, headquarters=""):
    """Active openings: undated ones, or published within OPENINGS_MAX_AGE_DAYS."""
    oldest_active = timezone.now() - timedelta(days=OPENINGS_MAX_AGE_DAYS)
    active_openings = [
        opening
        for opening in openings
        if opening.published_at is None or opening.published_at >= oldest_active
    ]
    status = OpeningsStatus.ACTIVE if active_openings else OpeningsStatus.NONE
    return OpeningsCheck(
        status, url=checked_url, openings=active_openings, headquarters=headquarters
    )


def startups_to_verify(include_checked=False):
    """Startups with something to check: a website hiring signal or a "Who is hiring?" post.

    By default only those never checked; `include_checked` checks them all again.
    """
    candidates = Startup.objects.filter(
        Q(website_inspection__has_hiring_signal=True)
        | Q(source_records__source__key=SourceKey.HACKER_NEWS_HIRING)
    ).distinct()
    if not include_checked:
        candidates = candidates.filter(
            Q(website_inspection__isnull=True)
            | Q(website_inspection__openings_status=OpeningsStatus.NOT_CHECKED)
        )
    return candidates.order_by("id")


def startups_due_for_openings_recheck():
    """Startups not discarded whose openings were checked more than OPENINGS_RECHECK_DAYS ago."""
    last_fresh_check = timezone.now() - timedelta(days=OPENINGS_RECHECK_DAYS)
    return (
        Startup.objects.exclude(status=StartupStatus.DISCARDED)
        .exclude(website_inspection__openings_status=OpeningsStatus.NOT_CHECKED)
        .filter(website_inspection__openings_checked_at__lt=last_fresh_check)
        .order_by("website_inspection__openings_checked_at")
    )
