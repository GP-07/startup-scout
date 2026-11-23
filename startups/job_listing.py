"""Reads open positions from a careers page and finds the job board a page uses.

Pure functions: no network and no database. A careers page lists openings as links to job pages
(on the same site or on a job board) or as schema.org `JobPosting` data. Applications that are
not an opening ("Talent pool", "General application") are left out.
"""

import html as html_entities
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from startups.constants import (
    GENERIC_APPLICATION_PHRASES,
    JOB_BOARD_DOMAINS,
    JOB_BOARD_JOB_PAGE_MIN_SEGMENTS,
    JOB_BOARD_PATTERNS,
    JOB_BOARD_RESERVED_SLUGS,
    JOB_BOARD_URLS,
    JOB_LOCATION_MAX_LENGTH,
    JOB_PAGE_PATH_PATTERN,
    JOB_SECTION_DOMAINS,
    JOB_TITLE_MAX_LENGTH,
    JOB_TITLE_TAGS,
    JOB_TITLE_WORDS,
    JSON_LD_JOB_POSTING_TYPE,
    JSON_LD_REMOTE_LOCATION_TYPE,
    JSON_LD_SCRIPT_TYPE,
    NO_OPENINGS_PHRASES,
    NON_VISIBLE_HTML_TAGS,
    OPEN_POSITIONS_LINK_PHRASES,
    REMOTE_WORDS,
    OpeningOrigin,
)
from startups.domains import normalize_domain
from startups.exceptions import InvalidWebsiteError
from startups.hiring_signal import normalize_text

PLATFORM_JOB_DOMAINS = JOB_BOARD_DOMAINS | JOB_SECTION_DOMAINS


@dataclass(frozen=True)
class OpeningCandidate:
    title: str
    location: str
    is_remote: bool | None
    url: str
    published_at: datetime | None
    origin: str


@dataclass(frozen=True)
class JobBoard:
    provider: str
    slug: str

    @property
    def public_url(self):
        return JOB_BOARD_URLS[self.provider].format(slug=self.slug)


def find_job_board(text):
    """The first Ashby, Greenhouse or Lever board mentioned in an HTML page or a URL."""
    unescaped_text = html_entities.unescape(text or "")
    matches = []
    for provider, pattern in JOB_BOARD_PATTERNS:
        for match in pattern.finditer(unescaped_text):
            if match.group(1).lower() not in JOB_BOARD_RESERVED_SLUGS:
                matches.append((match.start(), JobBoard(provider, match.group(1))))
                break
    return min(matches, key=_position)[1] if matches else None


def extract_openings(html, page_url):
    """Openings listed on a careers page, without generic applications, once per URL."""
    soup = BeautifulSoup(html, "html.parser")
    openings = _json_ld_openings(soup, page_url)
    for element in soup(NON_VISIBLE_HTML_TAGS):
        element.decompose()
    openings.extend(_linked_openings(soup, page_url))
    unique_openings = {}
    for opening in openings:
        if not is_generic_application(opening.title):
            unique_openings.setdefault(opening.url or opening.title, opening)
    return list(unique_openings.values())


def open_positions_links(html, page_url):
    """Links of the same site such as "See open positions", other than the page itself."""
    soup = BeautifulSoup(html, "html.parser")
    page_domain = _domain_or_none(page_url)
    current_page = _without_query(page_url).rstrip("/")
    links = []
    for link in soup.find_all("a", href=True):
        url = _without_query(urljoin(page_url, link["href"].strip()))
        link_text = normalize_text(link.get_text(" "))
        if url.rstrip("/") == current_page or _domain_or_none(url) != page_domain:
            continue
        names_open_positions = any(
            _contains_phrase(link_text, phrase) for phrase in OPEN_POSITIONS_LINK_PHRASES
        )
        if names_open_positions and url not in links:
            links.append(url)
    return links


def says_no_openings(html):
    """Whether the page states there are no open positions ("No open positions right now")."""
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(NON_VISIBLE_HTML_TAGS):
        element.decompose()
    page_text = normalize_text(soup.get_text(" "))
    return any(_contains_phrase(page_text, phrase) for phrase in NO_OPENINGS_PHRASES)


def is_generic_application(title):
    normalized_title = normalize_text(title)
    return any(_contains_phrase(normalized_title, phrase) for phrase in GENERIC_APPLICATION_PHRASES)


def is_remote_text(text):
    """True if the text says the job is remote; None when it does not say (not False)."""
    normalized_text = normalize_text(text or "")
    return True if any(_contains_phrase(normalized_text, word) for word in REMOTE_WORDS) else None


def parse_publication_date(value):
    """An ISO 8601 date or datetime as an aware datetime (UTC when it has no zone)."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _linked_openings(soup, page_url):
    page_domain = _domain_or_none(page_url)
    page_path = urlsplit(page_url).path.rstrip("/")
    for link in soup.find_all("a", href=True):
        url = urljoin(page_url, link["href"].strip())
        link_text = " ".join(link.get_text(" ").split())
        if not _names_a_job(link_text):
            continue
        if not (_is_job_page_of_site(url, page_domain, page_path) or _is_job_page_of_board(url)):
            continue
        yield OpeningCandidate(
            title=_link_title(link, link_text),
            location="",
            is_remote=is_remote_text(link_text),
            url=_without_query(url),
            published_at=None,
            origin=OpeningOrigin.WEBSITE,
        )


def _is_job_page_of_site(url, page_domain, page_path):
    """`/careers/backend-engineer` below the careers page, or `/jobs/<slug>` anywhere.

    On a job platform (YC, Wellfound) only jobs below the company's page count: its other
    links are the platform's own directory.
    """
    if page_domain is None or _domain_or_none(url) != page_domain:
        return False
    path = urlsplit(url).path.rstrip("/")
    below_page = bool(page_path) and path.startswith(page_path + "/")
    if page_domain in PLATFORM_JOB_DOMAINS:
        return below_page
    return below_page or bool(JOB_PAGE_PATH_PATTERN.search(path))


def _is_job_page_of_board(url):
    """A job's own page on a board (`jobs.ashbyhq.com/acme/<id>`), not the board itself."""
    if find_job_board(url) is None:
        return False
    path_segments = [segment for segment in urlsplit(url).path.split("/") if segment]
    return len(path_segments) >= JOB_BOARD_JOB_PAGE_MIN_SEGMENTS


def _names_a_job(link_text):
    normalized_text = normalize_text(link_text)
    return bool(normalized_text) and any(
        _contains_phrase(normalized_text, word) for word in JOB_TITLE_WORDS
    )


def _link_title(link, link_text):
    """The heading inside the link when there is one ("Backend Engineer"), else its text."""
    heading = link.find(JOB_TITLE_TAGS)
    title = " ".join(heading.get_text(" ").split()) if heading else link_text
    return title[:JOB_TITLE_MAX_LENGTH]


def _json_ld_openings(soup, page_url):
    openings = []
    for script in soup.find_all("script", type=JSON_LD_SCRIPT_TYPE):
        try:
            data = json.loads(script.get_text())
        except ValueError:
            continue
        for posting in _walk_job_postings(data):
            title = " ".join(str(posting.get("title") or "").split())
            if not title:
                continue
            openings.append(
                OpeningCandidate(
                    title=title[:JOB_TITLE_MAX_LENGTH],
                    location=_json_ld_location(posting)[:JOB_LOCATION_MAX_LENGTH],
                    is_remote=_json_ld_is_remote(posting),
                    url=str(posting.get("url") or page_url),
                    published_at=parse_publication_date(posting.get("datePosted")),
                    origin=OpeningOrigin.WEBSITE,
                )
            )
    return openings


def _walk_job_postings(node):
    if isinstance(node, list):
        for item in node:
            yield from _walk_job_postings(item)
        return
    if not isinstance(node, dict):
        return
    node_types = node.get("@type")
    node_types = node_types if isinstance(node_types, list) else [node_types]
    if JSON_LD_JOB_POSTING_TYPE in node_types:
        yield node
        return
    for value in node.values():
        yield from _walk_job_postings(value)


def _json_ld_location(posting):
    locations = posting.get("jobLocation")
    locations = locations if isinstance(locations, list) else [locations]
    names = []
    for location in locations:
        address = location.get("address") if isinstance(location, dict) else None
        if isinstance(address, dict):
            parts = [address.get("addressLocality"), address.get("addressCountry")]
            names.append(", ".join(str(part) for part in parts if isinstance(part, str) and part))
    return "; ".join(name for name in names if name)


def _json_ld_is_remote(posting):
    if posting.get("jobLocationType") == JSON_LD_REMOTE_LOCATION_TYPE:
        return True
    return is_remote_text(f"{posting.get('title', '')} {_json_ld_location(posting)}")


def _without_query(url):
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


def _contains_phrase(normalized_text, phrase):
    return f" {phrase} " in f" {normalized_text} "


def _domain_or_none(url):
    try:
        return normalize_domain(url)
    except InvalidWebsiteError:
        return None


def _position(match):
    return match[0]
