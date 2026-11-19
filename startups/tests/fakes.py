from sources.adapters.base import RawStartup


class FakeRedirectResolver:
    """Resolves URLs from a fixed mapping instead of the network."""

    def __init__(self, final_urls=None):
        self.final_urls = final_urls or {}

    def resolve_final_url(self, url):
        return self.final_urls.get(url)


def build_raw_startup(external_id, name, website="", **fields):
    return RawStartup(
        external_id=external_id,
        url=f"https://source.test/{external_id}",
        name=name,
        website=website,
        description=fields.get("description", ""),
        country=fields.get("country", ""),
        city=fields.get("city", ""),
        published_at=fields.get("published_at"),
        raw_payload=fields.get("raw_payload", {"id": external_id}),
    )
