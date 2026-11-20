"""Adding a startup by pasting its URL in the web UI."""

from sources.adapters.manual import ManualSourceAdapter
from sources.constants import SourceKey
from sources.models import Source
from startups.ingestion import StartupIngestionService
from startups.tasks import enqueue_website_inspection


def add_startup_manually(
    website, name="", ingestion_service=None, on_startup_created=enqueue_website_inspection
):
    """Ingest the URL as a manual source record; returns the `IngestionResult`.

    It goes through the same deduplication as every source: a known website returns the
    existing startup. Raises `InvalidWebsiteError` if the URL has no registrable domain.
    """
    raw_startup = ManualSourceAdapter().build_raw_startup(website, name=name)
    service = ingestion_service or StartupIngestionService()
    result = service.ingest(Source.objects.get(key=SourceKey.MANUAL), raw_startup)
    if result.created:
        on_startup_created(result.startup)
    return result
