"""Detects, from a page's HTML, signs that a startup has open positions.

Pure functions: no network and no database, so every rule is easy to test with fictitious HTML.
"""

import unicodedata
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from startups.constants import (
    HIRING_EMAIL_LOCAL_PARTS,
    HIRING_LINK_PHRASES,
    HIRING_LINK_WORDS,
    HIRING_PAGE_KEYWORDS,
    HIRING_PATH_EXCLUDED_SECTIONS,
    HIRING_PATH_PATTERN,
    HIRING_SIGNAL_KIND_PRIORITY,
    HIRING_SIGNAL_TEXT_MAX_LENGTH,
    HIRING_TEXT_PHRASES,
    JOB_BOARD_DOMAINS,
    JOB_SECTION_DOMAINS,
    JOB_SECTION_PATH_PATTERN,
    MAILTO_SCHEME,
    NON_ALPHANUMERIC_PATTERN,
    NON_VISIBLE_HTML_TAGS,
    HiringSignalKind,
)
from startups.domains import normalize_domain
from startups.exceptions import InvalidWebsiteError


@dataclass(frozen=True)
class HiringSignal:
    kind: str
    url: str
    text: str


def detect_hiring_signal(html, page_url):
    """Strongest hiring signal on the page, or None. See HiringSignalKind for the order."""
    soup = _parse(html)
    signals = [*_link_signals(soup, page_url), *_phrase_signals(soup, page_url)]
    if not signals:
        return None
    return min(signals, key=_signal_priority)


def visible_text(html):
    """Normalized visible text of a page, to compare pages and to look for keywords."""
    return normalize_text(_parse(html).get_text(" "))


def has_hiring_keywords(html):
    page_text = visible_text(html)
    return any(_contains_phrase(page_text, keyword) for keyword in HIRING_PAGE_KEYWORDS)


def normalize_text(text):
    """Lowercase, no accents, punctuation as spaces: `We’re Hiring!` -> `we re hiring`."""
    without_accents = "".join(
        character
        for character in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(character)
    )
    return " ".join(NON_ALPHANUMERIC_PATTERN.sub(" ", without_accents.lower()).split())


def _signal_priority(signal):
    return HIRING_SIGNAL_KIND_PRIORITY.index(signal.kind)


def _parse(html):
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(NON_VISIBLE_HTML_TAGS):
        element.decompose()
    return soup


def _link_signals(soup, page_url):
    page_domain = _domain_or_none(page_url)
    for link in soup.find_all("a", href=True):
        href = link["href"].strip()
        link_text = " ".join(link.get_text(" ").split())[:HIRING_SIGNAL_TEXT_MAX_LENGTH]
        if href.lower().startswith(MAILTO_SCHEME):
            if _is_hiring_email(href):
                yield HiringSignal(HiringSignalKind.EMAIL, href, link_text)
            continue
        absolute_url = urljoin(page_url, href)
        link_domain = _domain_or_none(absolute_url)
        if link_domain is None:
            continue
        path = urlsplit(absolute_url).path.lower()
        if _is_job_board(link_domain, path):
            yield HiringSignal(HiringSignalKind.JOB_BOARD, absolute_url, link_text)
        elif link_domain == page_domain and _is_hiring_path(path):
            yield HiringSignal(HiringSignalKind.LINK_PATH, absolute_url, link_text)
        elif _is_hiring_link_text(link_text):
            yield HiringSignal(HiringSignalKind.LINK_TEXT, absolute_url, link_text)


def _phrase_signals(soup, page_url):
    page_text = normalize_text(soup.get_text(" "))
    for phrase in HIRING_TEXT_PHRASES:
        if _contains_phrase(page_text, phrase):
            yield HiringSignal(HiringSignalKind.PHRASE, page_url, phrase)
            return


def _is_job_board(domain, path):
    if domain in JOB_BOARD_DOMAINS:
        return True
    return domain in JOB_SECTION_DOMAINS and bool(JOB_SECTION_PATH_PATTERN.search(path))


def _is_hiring_path(path):
    """`/careers` or `/company/jobs/`, but not `/docs/scheduler/jobs` or `/es/blog/careers`."""
    leading_segments = [segment for segment in path.split("/") if segment][:2]
    if any(segment in HIRING_PATH_EXCLUDED_SECTIONS for segment in leading_segments):
        return False
    return bool(HIRING_PATH_PATTERN.search(path))


def _is_hiring_link_text(link_text):
    normalized_text = normalize_text(link_text)
    if normalized_text in HIRING_LINK_WORDS:
        return True
    return any(_contains_phrase(normalized_text, phrase) for phrase in HIRING_LINK_PHRASES)


def _is_hiring_email(mailto_href):
    address = mailto_href[len(MAILTO_SCHEME) :].split("?")[0]
    local_part = address.split("@")[0].lower()
    return local_part in HIRING_EMAIL_LOCAL_PARTS


def _contains_phrase(normalized_text, phrase):
    """Whole-word match: `we re hiring` matches, `hiringx` does not."""
    return f" {phrase} " in f" {normalized_text} "


def _domain_or_none(url):
    try:
        return normalize_domain(url)
    except InvalidWebsiteError:
        return None
