"""Small helpers to read pages of a startup's website politely."""

from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from startups.constants import (
    HTML_CONTENT_TYPE,
    HTTP_OK,
    HTTP_SERVER_ERROR_MIN,
    ROBOTS_DISALLOW_ALL_STATUS_CODES,
    ROBOTS_TXT_PATH,
)


def load_robots(http_client, url):
    """Parsed robots.txt of the site of `url`. Missing file allows all; 401/403 and server
    errors disallow all. Network errors propagate (`httpx.HTTPError`)."""
    robots = RobotFileParser()
    response = http_client.get(site_root(url) + ROBOTS_TXT_PATH)
    if response.status_code == HTTP_OK:
        robots.parse(response.text.splitlines())
    elif (
        response.status_code in ROBOTS_DISALLOW_ALL_STATUS_CODES
        or response.status_code >= HTTP_SERVER_ERROR_MIN
    ):
        robots.disallow_all = True
    else:
        robots.allow_all = True
    return robots


def site_root(url):
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def html_of(response):
    """The response body if it is an HTML page, else ""."""
    content_type = response.headers.get("Content-Type", "")
    return response.text if HTML_CONTENT_TYPE in content_type else ""
