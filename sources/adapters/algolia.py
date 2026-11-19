"""Reads the public Hacker News search API (Algolia), shared by the Hacker News adapters."""

import httpx

from sources.constants import HACKER_NEWS_PAGE_SIZE, HACKER_NEWS_SEARCH_URL
from sources.exceptions import SourceFetchError


def fetch_algolia_hits(http_client, query_params):
    """Every hit of a `search_by_date` query, newest first, following its pages."""
    page = 0
    page_count = 1
    while page < page_count:
        params = {**query_params, "hitsPerPage": HACKER_NEWS_PAGE_SIZE, "page": page}
        try:
            response = http_client.get(HACKER_NEWS_SEARCH_URL, params=params)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise SourceFetchError(f"Hacker News request failed: {error}") from error
        yield from body.get("hits", [])
        page_count = body.get("nbPages", 0)
        page += 1


def created_after_filter(timestamp):
    return f"created_at_i>{timestamp}"
