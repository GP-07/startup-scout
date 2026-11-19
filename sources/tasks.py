import logging

from huey import crontab
from huey.contrib.djhuey import HUEY, db_periodic_task, db_task
from huey.exceptions import TaskLockedException

from sources.constants import DISCOVERY_HOUR, DISCOVERY_MINUTE, SOURCE_RUN_LOCK_PREFIX
from sources.models import Source
from sources.registry import runs_periodically
from sources.runner import SourceRunner

logger = logging.getLogger(__name__)


@db_periodic_task(crontab(hour=DISCOVERY_HOUR, minute=DISCOVERY_MINUTE))
def run_enabled_sources_task():
    """Daily discovery: one task per enabled source, so a failing source doesn't block others."""
    for source in Source.objects.filter(enabled=True).order_by("id"):
        if runs_periodically(source):
            run_source_task(source.id)


@db_task()
def run_source_task(source_id):
    source = Source.objects.get(pk=source_id)
    try:
        # Two runs of the same source at once would read the same cursor and repeat the work.
        with HUEY.lock_task(f"{SOURCE_RUN_LOCK_PREFIX}-{source.key}"):
            SourceRunner().run(source)
    except TaskLockedException:
        logger.info("Source %s is already running, skipping", source.key)
