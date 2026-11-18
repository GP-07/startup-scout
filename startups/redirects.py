import logging

import httpx

from startups.constants import (
    DEFAULT_URL_SCHEME,
    HEAD_FALLBACK_STATUS_CODES,
    REDIRECT_TIMEOUT_SECONDS,
    REDIRECT_USER_AGENT,
    URL_SCHEME_PATTERN,
)

logger = logging.getLogger(__name__)


class HttpRedirectResolver:
    """Follows a website's redirects to find its final URL (e.g. `acme.io` -> `acme.com`)."""

    def __init__(self, client=None):
        self.client = client or httpx.Client(
            follow_redirects=True,
            timeout=REDIRECT_TIMEOUT_SECONDS,
            headers={"User-Agent": REDIRECT_USER_AGENT},
        )

    def resolve_final_url(self, url):
        absolute_url = url if URL_SCHEME_PATTERN.match(url) else f"{DEFAULT_URL_SCHEME}{url}"
        try:
            response = self.client.head(absolute_url)
            if response.status_code in HEAD_FALLBACK_STATUS_CODES:
                with self.client.stream("GET", absolute_url) as streamed_response:
                    response = streamed_response
        except httpx.HTTPError as error:
            logger.info("Could not resolve redirects for %s: %s", absolute_url, error)
            return None
        return str(response.url)
