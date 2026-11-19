"""Visits a startup's own website to find signs of open positions and contacts.

Hiring (docs/startup-scout-design.md §3): the home page first, which usually settles it with a
single request; typical paths (/careers, /jobs...) only as a fallback.
Contacts (§5): the home plus the about, team and contact pages it links to, or typical paths of
those pages when it links none. robots.txt is respected throughout.
"""

import logging
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from django.utils import timezone

from startups.constants import (
    CONTACT_FALLBACK_PATHS,
    CONTACT_MAX_EXTRA_PAGES,
    DEFAULT_URL_SCHEME,
    HIRING_FALLBACK_PATHS,
    HIRING_SIGNAL_TEXT_MAX_LENGTH,
    HOME_PATHS,
    HTML_CONTENT_TYPE,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_SERVER_ERROR_MIN,
    INSPECTION_TIMEOUT_SECONDS,
    INSPECTION_USER_AGENT,
    ROBOTS_DISALLOW_ALL_STATUS_CODES,
    ROBOTS_TXT_PATH,
    ROBOTS_USER_AGENT_TOKEN,
    URL_SCHEME_PATTERN,
    ContactFoundVia,
    HiringSignalKind,
    HiringSignalMethod,
    InspectionStatus,
)
from startups.contact_extraction import contact_page_links, extract_contacts, merge_contacts
from startups.contacts import save_contacts
from startups.domains import normalize_domain
from startups.exceptions import InvalidWebsiteError
from startups.hiring_signal import (
    HiringSignal,
    detect_hiring_signal,
    has_hiring_keywords,
    visible_text,
)
from startups.models import WebsiteInspection
from startups.page_metrics import measure_page

logger = logging.getLogger(__name__)


def primary_domain(startup):
    """The startup's own primary domain, or None if it only has platform links (GitHub...)."""
    domain = startup.domains.filter(is_primary=True).values_list("domain", flat=True).first()
    return domain or None


def mark_inspection_pending(startup):
    inspection, _ = WebsiteInspection.objects.update_or_create(
        startup=startup, defaults={"status": InspectionStatus.PENDING}
    )
    return inspection


class WebsiteInspectionService:
    def __init__(self, http_client=None):
        self._http_client = http_client

    @property
    def http_client(self):
        if self._http_client is None:
            self._http_client = httpx.Client(
                follow_redirects=True,
                timeout=INSPECTION_TIMEOUT_SECONDS,
                headers={"User-Agent": INSPECTION_USER_AGENT},
            )
        return self._http_client

    def inspect(self, startup):
        """Inspect the startup's website and store the result. None if it has no own domain."""
        domain = primary_domain(startup)
        if domain is None:
            return None
        inspection, _ = WebsiteInspection.objects.get_or_create(startup=startup)
        home_url = f"https://{domain}/"
        try:
            robots = self._load_robots(home_url)
            if not robots.can_fetch(ROBOTS_USER_AGENT_TOKEN, home_url):
                return self._save(inspection, InspectionStatus.BLOCKED)
            home_response = self.http_client.get(home_url)
            if home_response.status_code == HTTP_NOT_FOUND:
                # GitHub Pages and similar: the site lives under a path, not at the root.
                home_response = self._get_website_page(startup, domain, robots) or home_response
            home_response.raise_for_status()
        except httpx.HTTPError as error:
            logger.info("Could not inspect %s: %s", home_url, error)
            return self._save(inspection, InspectionStatus.FAILED, error=str(error))

        home_html = _html_of(home_response)
        signal = detect_hiring_signal(home_html, str(home_response.url))
        method = HiringSignalMethod.HOME if signal else ""
        if signal is None:
            signal = self._probe_typical_paths(home_response, home_html, robots)
            method = HiringSignalMethod.PATH_PROBE if signal else ""
        contacts_found = self._collect_contacts(startup, home_response, home_html, robots)
        return self._save(
            inspection,
            InspectionStatus.DONE,
            signal=signal,
            method=method,
            home_metrics=measure_page(home_html),
            contacts_found=contacts_found,
        )

    def _get_website_page(self, startup, domain, robots):
        """The startup's own website URL, when it is a page of the same domain below the root."""
        website_url = _absolute_url(startup.website)
        try:
            same_domain = normalize_domain(website_url) == domain
        except InvalidWebsiteError:
            return None
        if not same_domain or urlsplit(website_url).path in HOME_PATHS:
            return None
        if not robots.can_fetch(ROBOTS_USER_AGENT_TOKEN, website_url):
            return None
        return self.http_client.get(website_url)

    def _load_robots(self, home_url):
        """Parsed robots.txt. Missing file allows all; 401/403 and server errors disallow all."""
        robots = RobotFileParser()
        robots_url = _site_root(home_url) + ROBOTS_TXT_PATH
        response = self.http_client.get(robots_url)
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

    def _probe_typical_paths(self, home_response, home_html, robots):
        site_root = _site_root(str(home_response.url))
        home_text = visible_text(home_html)
        for path in HIRING_FALLBACK_PATHS:
            probe_url = site_root + path
            if not robots.can_fetch(ROBOTS_USER_AGENT_TOKEN, probe_url):
                continue
            try:
                response = self.http_client.get(probe_url)
            except httpx.HTTPError as error:
                logger.info("Could not probe %s: %s", probe_url, error)
                continue
            if _is_hiring_page(response, site_root, home_text):
                return HiringSignal(
                    kind=HiringSignalKind.LINK_PATH,
                    url=str(response.url),
                    text=_page_title(response),
                )
        return None

    def _collect_contacts(self, startup, home_response, home_html, robots):
        """Find contacts on the home and on its contact pages; return how many were found."""
        home_url = str(home_response.url)
        site_root = _site_root(home_url)
        home_text = visible_text(home_html)
        candidates = list(extract_contacts(home_html, home_url))
        page_urls = contact_page_links(home_html, home_url) or [
            site_root + path for path in CONTACT_FALLBACK_PATHS
        ]
        for page_url in page_urls[:CONTACT_MAX_EXTRA_PAGES]:
            if not robots.can_fetch(ROBOTS_USER_AGENT_TOKEN, page_url):
                continue
            try:
                response = self.http_client.get(page_url)
            except httpx.HTTPError as error:
                logger.info("Could not read %s: %s", page_url, error)
                continue
            if _is_own_page(response, site_root, home_text):
                candidates.extend(extract_contacts(_html_of(response), str(response.url)))
        contacts = merge_contacts(candidates)
        save_contacts(startup, contacts, ContactFoundVia.WEBSITE)
        return len(contacts)

    def _save(
        self,
        inspection,
        status,
        signal=None,
        method="",
        error="",
        home_metrics=None,
        contacts_found=0,
    ):
        inspection.status = status
        inspection.inspected_at = timezone.now()
        inspection.has_hiring_signal = signal is not None
        inspection.hiring_signal_method = method if signal else ""
        inspection.hiring_signal_kind = signal.kind if signal else ""
        inspection.hiring_signal_url = signal.url if signal else ""
        inspection.hiring_signal_text = (
            signal.text[:HIRING_SIGNAL_TEXT_MAX_LENGTH] if signal else ""
        )
        inspection.home_text_length = home_metrics.text_length if home_metrics else None
        inspection.home_link_count = home_metrics.link_count if home_metrics else None
        inspection.home_has_app_root = home_metrics.has_app_root if home_metrics else None
        inspection.contacts_found = contacts_found
        inspection.error = error
        inspection.save()
        return inspection


def _is_hiring_page(response, site_root, home_text):
    """A probed path counts only if it is a real page of its own with hiring words."""
    return _is_own_page(response, site_root, home_text) and has_hiring_keywords(_html_of(response))


def _is_own_page(response, site_root, home_text):
    """A page of the site other than the home, not a redirect to it nor the same SPA shell."""
    if response.status_code != HTTP_OK:
        return False
    final_url = urlsplit(str(response.url))
    if _site_root(str(response.url)) != site_root or final_url.path in HOME_PATHS:
        return False  # Redirected to the home page or to another site.
    page_html = _html_of(response)
    # Single-page apps serve the same shell for every path.
    return bool(page_html) and visible_text(page_html) != home_text


def _html_of(response):
    content_type = response.headers.get("Content-Type", "")
    return response.text if HTML_CONTENT_TYPE in content_type else ""


def _page_title(response):
    title = BeautifulSoup(response.text, "html.parser").title
    if title is None or not title.get_text(strip=True):
        return urlsplit(str(response.url)).path
    return title.get_text(strip=True)


def _absolute_url(website):
    value = (website or "").strip()
    return value if URL_SCHEME_PATTERN.match(value) else f"{DEFAULT_URL_SCHEME}{value}"


def _site_root(url):
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"
