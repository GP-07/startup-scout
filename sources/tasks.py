import logging

from django.utils import timezone
from huey import crontab
from huey.contrib.djhuey import HUEY, db_periodic_task, db_task
from huey.exceptions import TaskLockedException

from sources.constants import (
    DISCOVERY_CHECK_MINUTE,
    DISCOVERY_HOUR,
    SOURCE_RUN_LOCK_PREFIX,
    SourceRunStatus,
)
from sources.models import Source, SourceRun
from sources.registry import runs_periodically
from sources.runner import SourceRunner

logger = logging.getLogger(__name__)


@db_periodic_task(crontab(minute=DISCOVERY_CHECK_MINUTE))
def run_enabled_sources_task():
    """Daily discovery, checked every hour so a missed run is caught up.

    Huey fires a periodic task only if the worker is awake at that exact minute: with the
    computer asleep at the discovery hour, the day would be lost. So every hour, from the
    discovery hour on (Madrid time, the project's TIME_ZONE), each enabled source that has not
    succeeded yet today is run. One task per source, so a failing source doesn't block others.
    """
    now = timezone.localtime(timezone.now())
    if now.hour < DISCOVERY_HOUR:
        return
    todays_discovery = now.replace(hour=DISCOVERY_HOUR, minute=0, second=0, microsecond=0)
    sources_done_today = SourceRun.objects.filter(
        status=SourceRunStatus.SUCCEEDED, started_at__gte=todays_discovery
    ).values("source_id")
    due_sources = (
        Source.objects.filter(enabled=True).exclude(id__in=sources_done_today).order_by("id")
    )
    for source in due_sources:
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
