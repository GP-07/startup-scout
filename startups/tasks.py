from huey.contrib.djhuey import db_task

from startups.models import Startup
from startups.website_inspection import (
    WebsiteInspectionService,
    mark_inspection_pending,
    primary_domain,
)


@db_task()
def inspect_website_task(startup_id):
    startup = Startup.objects.filter(pk=startup_id).first()
    if startup is not None:
        WebsiteInspectionService().inspect(startup)


def enqueue_website_inspection(startup):
    """Schedule the inspection of a startup's website. Startups without own domain are skipped."""
    if primary_domain(startup) is None:
        return
    mark_inspection_pending(startup)
    inspect_website_task(startup.id)
