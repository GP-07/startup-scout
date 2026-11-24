import logging
from dataclasses import dataclass

from django.db import IntegrityError, transaction

from sources.models import SourceRecord
from startups.blacklist import blacklist_reason
from startups.constants import MAX_INGESTION_ATTEMPTS, ContactFoundVia
from startups.contacts import save_contacts
from startups.domains import is_identifying_domain, normalize_domain, normalize_name
from startups.exceptions import IngestionConflictError, InvalidWebsiteError
from startups.merge import recompute_startup
from startups.models import Startup, StartupDomain
from startups.redirects import HttpRedirectResolver
from startups.status import discard_startup

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionResult:
    startup: Startup
    created: bool
    record_created: bool


class StartupIngestionService:
    """Turns what a source reports into a single, deduplicated startup.

    Identity is the normalized domain, including the domain the website redirects to.
    Startups without a usable website are never merged automatically: a name match only flags
    them as possible duplicates.
    """

    def __init__(self, redirect_resolver=None):
        self.redirect_resolver = redirect_resolver or HttpRedirectResolver()

    def ingest(self, source, raw_startup):
        # Network calls happen before the transaction, so it stays short.
        domains = self._collect_domains(raw_startup.website)
        for attempt in range(1, MAX_INGESTION_ATTEMPTS + 1):
            try:
                with transaction.atomic():
                    return self._ingest_once(source, raw_startup, domains)
            except IntegrityError:
                # Another ingestion created the same domain or record first: retry, now it matches.
                logger.info(
                    "Concurrent ingestion of %s:%s (attempt %s)",
                    source.key,
                    raw_startup.external_id,
                    attempt,
                )
        raise IngestionConflictError(source.key, raw_startup.external_id)

    def _collect_domains(self, website):
        """Domains that identify the startup, the canonical one (after redirects) first."""
        if not website:
            return []
        try:
            original_domain = normalize_domain(website)
        except InvalidWebsiteError:
            logger.info("Ignoring website without registrable domain: %s", website)
            return []
        if not is_identifying_domain(original_domain):
            # A GitHub repository or an app store page: the domain belongs to the platform.
            return []

        final_url = self.redirect_resolver.resolve_final_url(website)
        if not final_url:
            return [original_domain]
        try:
            final_domain = normalize_domain(final_url)
        except InvalidWebsiteError:
            return [original_domain]
        if final_domain == original_domain or not is_identifying_domain(final_domain):
            return [original_domain]
        return [final_domain, original_domain]

    def _ingest_once(self, source, raw_startup, domains):
        existing_record = (
            SourceRecord.objects.select_for_update()
            .select_related("startup")
            .filter(source=source, external_id=raw_startup.external_id)
            .first()
        )
        if existing_record is not None:
            self._update_record(existing_record, raw_startup)
            self._attach_domains(existing_record.startup, domains)
            save_contacts(existing_record.startup, raw_startup.contacts, ContactFoundVia.SOURCE)
            startup = recompute_startup(existing_record.startup)
            return IngestionResult(startup=startup, created=False, record_created=False)

        startup = self._find_by_domains(domains)
        created = startup is None
        if created:
            startup = self._create_startup(raw_startup, domains)
        self._attach_domains(startup, domains)
        SourceRecord.objects.create(
            source=source,
            startup=startup,
            external_id=raw_startup.external_id,
            url=raw_startup.url,
            data=raw_startup.mergeable_data(),
            payload=raw_startup.raw_payload,
            published_at=raw_startup.published_at,
        )
        save_contacts(startup, raw_startup.contacts, ContactFoundVia.SOURCE)
        startup = recompute_startup(startup)
        reason = blacklist_reason(domains) if created else ""
        if reason:
            # A blacklisted site (a job board): it comes in already discarded.
            discard_startup(startup, reason)
        return IngestionResult(startup=startup, created=created, record_created=True)

    def _find_by_domains(self, domains):
        if not domains:
            return None
        matched_startups = list(
            Startup.objects.filter(domains__domain__in=domains).distinct().order_by("id")
        )
        if not matched_startups:
            return None
        oldest_startup, *other_startups = matched_startups
        for other_startup in other_startups:
            # The domains connect startups that were created apart: flag them, never auto-merge.
            if other_startup.possible_duplicate_of_id is None:
                other_startup.possible_duplicate_of = oldest_startup
                other_startup.save(update_fields=["possible_duplicate_of", "updated_at"])
        return oldest_startup

    def _create_startup(self, raw_startup, domains):
        name = raw_startup.name or (domains[0] if domains else raw_startup.external_id)
        normalized_name = normalize_name(name)
        same_name_startup = (
            Startup.objects.filter(normalized_name=normalized_name).order_by("id").first()
            if normalized_name
            else None
        )
        return Startup.objects.create(
            name=name,
            normalized_name=normalized_name,
            website=raw_startup.website,
            possible_duplicate_of=same_name_startup,
        )

    def _attach_domains(self, startup, domains):
        has_primary_domain = startup.domains.filter(is_primary=True).exists()
        taken_domains = set(
            StartupDomain.objects.filter(domain__in=domains).values_list("domain", flat=True)
        )
        for domain in domains:
            if domain in taken_domains:
                continue
            StartupDomain.objects.create(
                startup=startup, domain=domain, is_primary=not has_primary_domain
            )
            has_primary_domain = True

    def _update_record(self, record, raw_startup):
        record.url = raw_startup.url
        record.data = raw_startup.mergeable_data()
        record.payload = raw_startup.raw_payload
        record.published_at = raw_startup.published_at
        record.save(update_fields=["url", "data", "payload", "published_at", "fetched_at"])
