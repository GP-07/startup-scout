"""Brings stored domains in line with the current identity rules.

When a platform is added to NON_IDENTIFYING_DOMAINS or SHARED_HOST_DOMAINS, startups ingested
before still carry that platform's domain (e.g. `jetbrains.com` for a plugin page). This removes
those domains, drops their website inspection (it inspected the platform, not the startup) and
assigns the startup its own domain again from its source records, when there is one.
"""

from dataclasses import dataclass

from django.db import transaction

from startups.domains import is_identifying_domain, normalize_domain
from startups.exceptions import InvalidWebsiteError
from startups.models import StartupDomain, WebsiteInspection


@dataclass(frozen=True)
class DomainCleanupResult:
    removed_domains: list
    reassigned_domains: list


@transaction.atomic
def prune_platform_domains():
    platform_domains = [
        startup_domain
        for startup_domain in StartupDomain.objects.select_related("startup")
        if not is_identifying_domain(startup_domain.domain)
    ]
    affected_startups = {startup_domain.startup for startup_domain in platform_domains}
    removed_domains = sorted(startup_domain.domain for startup_domain in platform_domains)
    StartupDomain.objects.filter(pk__in=[domain.pk for domain in platform_domains]).delete()
    WebsiteInspection.objects.filter(startup__in=affected_startups).delete()

    reassigned_domains = []
    for startup in sorted(affected_startups, key=_startup_id):
        if startup.domains.filter(is_primary=True).exists():
            continue
        remaining_domain = startup.domains.order_by("id").first()
        if remaining_domain is not None:
            # The platform was the redirect target; the startup's own domain was kept as alias.
            remaining_domain.is_primary = True
            remaining_domain.save(update_fields=["is_primary"])
            reassigned_domains.append(remaining_domain.domain)
            continue
        own_domain = _own_domain_from_records(startup)
        if own_domain and not StartupDomain.objects.filter(domain=own_domain).exists():
            StartupDomain.objects.create(startup=startup, domain=own_domain, is_primary=True)
            reassigned_domains.append(own_domain)
    return DomainCleanupResult(
        removed_domains=removed_domains, reassigned_domains=reassigned_domains
    )


def _own_domain_from_records(startup):
    for website in startup.source_records.values_list("data__website", flat=True):
        try:
            domain = normalize_domain(website or "")
        except InvalidWebsiteError:
            continue
        if is_identifying_domain(domain):
            return domain
    return None


def _startup_id(startup):
    return startup.id
