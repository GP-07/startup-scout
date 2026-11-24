"""A blacklist of sites that are not startups, such as job boards the rules could not detect.

A blacklisted startup is discarded with the reason, loses its openings and is never inspected
nor verified again (discarded startups are skipped). A source that reports one of its domains
again creates the startup already discarded (startups/ingestion.py).
"""

from django.db import transaction

from startups.constants import BLACKLIST_DEFAULT_REASON, OpeningsStatus, StartupStatus
from startups.models import BlacklistedDomain, WebsiteInspection
from startups.status import discard_startup


@transaction.atomic
def blacklist_startup(startup, reason=BLACKLIST_DEFAULT_REASON):
    """Blacklist every domain of the startup and discard it."""
    for domain in startup.domains.values_list("domain", flat=True):
        blacklist_domain(domain, reason)
    startup.job_openings.all().delete()
    WebsiteInspection.objects.filter(startup=startup, openings_status=OpeningsStatus.ACTIVE).update(
        openings_status=OpeningsStatus.NONE
    )
    if startup.status != StartupStatus.DISCARDED:
        discard_startup(startup, reason)
    return startup


def blacklist_domain(domain, reason=BLACKLIST_DEFAULT_REASON):
    entry, _ = BlacklistedDomain.objects.update_or_create(
        domain=domain, defaults={"reason": reason}
    )
    return entry


def blacklist_reason(domains):
    """The reason a blacklisted domain among these has, or blank if none is blacklisted."""
    entry = BlacklistedDomain.objects.filter(domain__in=domains).first()
    return entry.reason if entry else ""
