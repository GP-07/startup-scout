import html
import logging
from datetime import timedelta

import httpx
from django.utils import timezone

from sources.adapters.base import RawStartup, SourceAdapter, SourceFetchResult
from sources.constants import (
    HACKER_NEWS_CURSOR_KEY,
    HACKER_NEWS_CURSOR_OVERLAP_SECONDS,
    HACKER_NEWS_DESCRIPTION_MAX_LENGTH,
    HACKER_NEWS_IGNORED_PAYLOAD_KEYS,
    HACKER_NEWS_INITIAL_LOOKBACK_DAYS,
    HACKER_NEWS_ITEM_URL,
    HACKER_NEWS_PAGE_SIZE,
    HACKER_NEWS_QUERIES,
    HACKER_NEWS_SEARCH_URL,
    HACKER_NEWS_TITLE_SEPARATORS,
    HTML_LINK_PATTERN,
    HTML_TAG_PATTERN,
    WHITESPACE_PATTERN,
    YC_BATCH_PATTERN,
)
from sources.exceptions import SourceFetchError
from startups.domains import is_identifying_domain, normalize_domain
from startups.exceptions import InvalidWebsiteError

logger = logging.getLogger(__name__)


class HackerNewsAdapter(SourceAdapter):
    """Reads "Show HN" and "Launch HN" posts from the public Algolia API.

    Config: `tags` (keys of HACKER_NEWS_QUERIES) and optionally `initial_lookback_days`.
    Cursor: `created_at_i` of the newest post seen.
    """

    def fetch_candidates(self, cursor):
        last_seen_timestamp = cursor.get(HACKER_NEWS_CURSOR_KEY)
        if last_seen_timestamp:
            # Algolia can index a post late: re-read a short window. Repeats are just updates.
            since_timestamp = last_seen_timestamp - HACKER_NEWS_CURSOR_OVERLAP_SECONDS
            newest_timestamp = last_seen_timestamp
        else:
            since_timestamp = newest_timestamp = self._initial_timestamp()
        raw_startups_by_id = {}
        for tag in self.config.get("tags", list(HACKER_NEWS_QUERIES)):
            query = HACKER_NEWS_QUERIES.get(tag)
            if query is None:
                raise SourceFetchError(f"Unknown Hacker News tag '{tag}'")
            for hit in self._fetch_hits(query["params"], since_timestamp):
                newest_timestamp = max(newest_timestamp, hit["created_at_i"])
                if not (hit.get("title") or "").startswith(query["title_prefix"]):
                    continue
                raw_startup = self._to_raw_startup(hit, query["title_prefix"])
                raw_startups_by_id[raw_startup.external_id] = raw_startup
        return SourceFetchResult(
            raw_startups=list(raw_startups_by_id.values()),
            cursor={HACKER_NEWS_CURSOR_KEY: newest_timestamp},
        )

    def _initial_timestamp(self):
        lookback_days = self.config.get("initial_lookback_days", HACKER_NEWS_INITIAL_LOOKBACK_DAYS)
        return int((timezone.now() - timedelta(days=lookback_days)).timestamp())

    def _fetch_hits(self, query_params, since_timestamp):
        page = 0
        page_count = 1
        while page < page_count:
            params = {
                **query_params,
                "numericFilters": f"created_at_i>{since_timestamp}",
                "hitsPerPage": HACKER_NEWS_PAGE_SIZE,
                "page": page,
            }
            try:
                response = self.http_client.get(HACKER_NEWS_SEARCH_URL, params=params)
                response.raise_for_status()
                body = response.json()
            except (httpx.HTTPError, ValueError) as error:
                raise SourceFetchError(f"Hacker News request failed: {error}") from error
            yield from body.get("hits", [])
            page_count = body.get("nbPages", 0)
            page += 1

    def _to_raw_startup(self, hit, title_prefix):
        title_without_prefix = hit["title"][len(title_prefix) :].strip()
        name, tagline = _split_title(title_without_prefix)
        story_text = hit.get("story_text") or ""
        return RawStartup(
            external_id=str(hit["objectID"]),
            url=HACKER_NEWS_ITEM_URL.format(item_id=hit["objectID"]),
            name=YC_BATCH_PATTERN.sub("", name),
            website=_choose_website(hit.get("url") or "", story_text),
            description=tagline or _plain_text(story_text)[:HACKER_NEWS_DESCRIPTION_MAX_LENGTH],
            raw_payload={
                key: value
                for key, value in hit.items()
                if key not in HACKER_NEWS_IGNORED_PAYLOAD_KEYS
            },
        )


def _split_title(title):
    """`Acme – Invoices for you` -> (`Acme`, `Invoices for you`); no separator -> (title, "")."""
    separator_positions = [
        (title.find(separator), separator)
        for separator in HACKER_NEWS_TITLE_SEPARATORS
        if title.find(separator) > 0
    ]
    if not separator_positions:
        return title, ""
    position, separator = min(separator_positions)
    return title[:position].strip(), title[position + len(separator) :].strip()


def _choose_website(post_url, story_text):
    """The post link if it is the startup's own site, else the first own site linked in the text.

    Show HN posts often link a GitHub repository and mention the real site in the text.
    """
    linked_urls = [html.unescape(link) for link in HTML_LINK_PATTERN.findall(story_text)]
    for candidate_url in [post_url, *linked_urls]:
        if candidate_url and _has_identifying_domain(candidate_url):
            return candidate_url
    return post_url


def _has_identifying_domain(url):
    try:
        return is_identifying_domain(normalize_domain(url))
    except InvalidWebsiteError:
        return False


def _plain_text(story_text):
    without_tags = HTML_TAG_PATTERN.sub(" ", story_text)
    return WHITESPACE_PATTERN.sub(" ", html.unescape(without_tags)).strip()
