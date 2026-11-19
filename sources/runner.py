import logging

from django.utils import timezone

from sources.constants import SourceRunStatus
from sources.exceptions import SourceFetchError, UnknownSourceError
from sources.models import SourceRun
from sources.registry import get_adapter
from startups.ingestion import StartupIngestionService
from startups.tasks import enqueue_website_inspection

logger = logging.getLogger(__name__)


class SourceRunner:
    """Runs one source end to end: fetch from the adapter, ingest each startup, record the run.

    The cursor only moves forward when the fetch succeeds. A startup that fails to ingest is
    logged in the run's `error` and does not stop the others. Each startup created is handed to
    `on_startup_created` (by default, it schedules the inspection of its website).
    """

    def __init__(self, ingestion_service=None, on_startup_created=enqueue_website_inspection):
        self.ingestion_service = ingestion_service or StartupIngestionService()
        self.on_startup_created = on_startup_created

    def run(self, source):
        source_run = SourceRun.objects.create(source=source)
        try:
            fetch_result = get_adapter(source).fetch_candidates(self._last_cursor(source))
        except (SourceFetchError, UnknownSourceError) as error:
            logger.warning("Source %s could not be fetched: %s", source.key, error)
            return self._finish(source_run, SourceRunStatus.FAILED, error=str(error))

        ingestion_errors = []
        for raw_startup in fetch_result.raw_startups:
            source_run.items_seen += 1
            try:
                ingestion_result = self.ingestion_service.ingest(source, raw_startup)
            except Exception as error:  # noqa: BLE001 - one bad item must not stop the run
                logger.exception("Could not ingest %s:%s", source.key, raw_startup.external_id)
                ingestion_errors.append(f"{raw_startup.external_id}: {error}")
                continue
            if ingestion_result.created:
                source_run.items_new += 1
                self.on_startup_created(ingestion_result.startup)

        source_run.cursor = fetch_result.cursor
        return self._finish(
            source_run, SourceRunStatus.SUCCEEDED, error="\n".join(ingestion_errors)
        )

    def _last_cursor(self, source):
        last_successful_run = (
            SourceRun.objects.filter(source=source, status=SourceRunStatus.SUCCEEDED)
            .order_by("-started_at", "-id")
            .first()
        )
        return last_successful_run.cursor if last_successful_run else {}

    def _finish(self, source_run, status, error=""):
        source_run.status = status
        source_run.error = error
        source_run.finished_at = timezone.now()
        source_run.save()
        return source_run
