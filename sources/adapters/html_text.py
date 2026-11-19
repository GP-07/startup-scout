"""Helpers for the HTML snippets Hacker News stores (post texts and comments)."""

import html
from datetime import UTC, datetime

from sources.constants import HTML_LINK_PATTERN, HTML_TAG_PATTERN, WHITESPACE_PATTERN
from startups.domains import is_identifying_domain, normalize_domain
from startups.exceptions import InvalidWebsiteError


def plain_text(html_text):
    without_tags = HTML_TAG_PATTERN.sub(" ", html_text or "")
    return WHITESPACE_PATTERN.sub(" ", html.unescape(without_tags)).strip()


def extract_links(html_text):
    return [html.unescape(link) for link in HTML_LINK_PATTERN.findall(html_text or "")]


def identifying_domain(url):
    """The startup domain a URL points to, or None for platforms and invalid values."""
    try:
        domain = normalize_domain(url)
    except InvalidWebsiteError:
        return None
    return domain if is_identifying_domain(domain) else None


def timestamp_to_datetime(timestamp):
    return datetime.fromtimestamp(timestamp, tz=UTC) if timestamp else None
