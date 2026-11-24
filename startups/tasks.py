import logging

from huey import crontab
from huey.contrib.djhuey import HUEY, db_periodic_task, db_task
from huey.exceptions import TaskLockedException

from startups.constants import (
    OPENINGS_RECHECK_BATCH,
    OPENINGS_RECHECK_LOCK,
    OPENINGS_RECHECK_MINUTE,
    StartupStatus,
)
from startups.models import Startup
from startups.openings import OpeningsVerifier, startups_due_for_openings_recheck
from startups.website_inspection import (
    WebsiteInspectionService,
    mark_inspection_pending,
    primary_domain,
)

logger = logging.getLogger(__name__)


@db_task()
def inspect_website_task(startup_id):
    startup = Startup.objects.filter(pk=startup_id).first()
    if startup is not None:
        WebsiteInspectionService().inspect(startup)


def enqueue_website_inspection(startup):
    """Schedule the inspection of a startup's website.

    Startups without own domain are skipped, and so are discarded ones (a blacklisted site).
    """
    if startup.status == StartupStatus.DISCARDED or primary_domain(startup) is None:
        return
    mark_inspection_pending(startup)
    inspect_website_task(startup.id)


@db_periodic_task(crontab(minute=OPENINGS_RECHECK_MINUTE))
def recheck_openings_task():
    """Every hour, check again a batch of startups whose openings are a week old.

    Openings close and open: one no longer published stops counting. Hourly batches spread the
    requests and catch up after the computer slept.
    """
    try:
        with HUEY.lock_task(OPENINGS_RECHECK_LOCK):
            verifier = OpeningsVerifier()
            for startup in startups_due_for_openings_recheck()[:OPENINGS_RECHECK_BATCH]:
                verifier.verify(startup)
    except TaskLockedException:
        logger.info("Openings recheck already running, skipping")
