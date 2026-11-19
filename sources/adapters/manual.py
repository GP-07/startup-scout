from sources.adapters.base import RawStartup, SourceAdapter, SourceFetchResult
from startups.domains import normalize_domain, normalize_url


class ManualSourceAdapter(SourceAdapter):
    """Startups I add by pasting a URL in the web UI. Nothing to fetch periodically."""

    runs_periodically = False

    def fetch_candidates(self, cursor):
        return SourceFetchResult(raw_startups=[], cursor=cursor)

    def build_raw_startup(self, website, name=""):
        """Raise `InvalidWebsiteError` if the URL has no registrable domain."""
        domain = normalize_domain(website)
        return RawStartup(
            external_id=normalize_url(website),
            url="",
            name=name.strip() or domain.split(".")[0].capitalize(),
            website=website.strip(),
            raw_payload={"website": website, "name": name},
        )
