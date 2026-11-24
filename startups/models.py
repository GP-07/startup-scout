from django.db import models

from startups.constants import (
    ContactFoundVia,
    ContactRole,
    ContactStatus,
    HiringSignalKind,
    HiringSignalMethod,
    InspectionStatus,
    LocationSource,
    OpeningOrigin,
    OpeningsStatus,
    RemotePolicy,
    StartupStatus,
)
from startups.querysets import StartupQuerySet


class Startup(models.Model):
    name = models.CharField(max_length=255)
    normalized_name = models.CharField(max_length=255, db_index=True, blank=True)
    website = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    country = models.CharField(max_length=2, blank=True, help_text="ISO 3166-1 alpha-2")
    city = models.CharField(max_length=255, blank=True)
    remote_policy = models.CharField(
        max_length=20, choices=RemotePolicy.choices, default=RemotePolicy.UNKNOWN
    )
    status = models.CharField(
        max_length=30, choices=StartupStatus.choices, default=StartupStatus.NEW, db_index=True
    )
    discard_reason = models.CharField(max_length=255, blank=True)
    possible_duplicate_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="possible_duplicates",
    )
    field_sources = models.JSONField(default=dict, blank=True)
    # Where it is established (startups/headquarters.py): blank while unknown. The zone is the
    # city's when known, else the capital's; it gives the time difference from Madrid.
    hq_country = models.CharField(
        max_length=2, blank=True, db_index=True, help_text="ISO 3166-1 alpha-2"
    )
    hq_city = models.CharField(max_length=255, blank=True)
    hq_timezone = models.CharField(max_length=64, blank=True, db_index=True, help_text="IANA")
    location_source = models.CharField(max_length=20, choices=LocationSource.choices, blank=True)
    location_evidence = models.CharField(max_length=500, blank=True)
    location_detected_at = models.DateTimeField(null=True, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = StartupQuerySet.as_manager()

    class Meta:
        ordering = ["-first_seen_at"]

    def __str__(self):
        return self.name


class StartupDomain(models.Model):
    startup = models.ForeignKey(Startup, on_delete=models.CASCADE, related_name="domains")
    domain = models.CharField(max_length=255, unique=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "domain"]

    def __str__(self):
        return self.domain


class StatusChange(models.Model):
    startup = models.ForeignKey(Startup, on_delete=models.CASCADE, related_name="status_changes")
    from_status = models.CharField(max_length=30, choices=StartupStatus.choices)
    to_status = models.CharField(max_length=30, choices=StartupStatus.choices)
    note = models.CharField(max_length=255, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.startup}: {self.from_status} -> {self.to_status}"


class Contact(models.Model):
    startup = models.ForeignKey(Startup, on_delete=models.CASCADE, related_name="contacts")
    full_name = models.CharField(max_length=255, blank=True)
    role = models.CharField(max_length=20, choices=ContactRole.choices, default=ContactRole.OTHER)
    email = models.EmailField(blank=True)
    profile_url = models.URLField(max_length=500, blank=True)
    found_via = models.CharField(max_length=20, choices=ContactFoundVia.choices)
    evidence_url = models.URLField(max_length=500, blank=True)
    status = models.CharField(
        max_length=20, choices=ContactStatus.choices, default=ContactStatus.CANDIDATE
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["status", "role", "full_name"]

    def __str__(self):
        return self.full_name or self.email or self.profile_url


class Analysis(models.Model):
    startup = models.ForeignKey(Startup, on_delete=models.CASCADE, related_name="analyses")
    title = models.CharField(max_length=255)
    body = models.TextField(help_text="Markdown")
    sent_at = models.DateTimeField(null=True, blank=True)
    sent_to = models.ForeignKey(
        Contact, null=True, blank=True, on_delete=models.SET_NULL, related_name="analyses_sent"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "analyses"

    def __str__(self):
        return self.title

    @property
    def is_sent(self):
        return self.sent_at is not None


class WebsiteInspection(models.Model):
    """Result of visiting the startup's own website: today, whether it shows open positions."""

    startup = models.OneToOneField(
        Startup, on_delete=models.CASCADE, related_name="website_inspection"
    )
    status = models.CharField(
        max_length=20, choices=InspectionStatus.choices, default=InspectionStatus.PENDING
    )
    inspected_at = models.DateTimeField(null=True, blank=True)
    has_hiring_signal = models.BooleanField(default=False, db_index=True)
    hiring_signal_method = models.CharField(
        max_length=20, choices=HiringSignalMethod.choices, blank=True
    )
    hiring_signal_kind = models.CharField(
        max_length=20, choices=HiringSignalKind.choices, blank=True
    )
    hiring_signal_url = models.URLField(max_length=500, blank=True)
    hiring_signal_text = models.CharField(max_length=255, blank=True)
    # What the home page shows without JavaScript (startups/page_metrics.py). Null if not read.
    home_text_length = models.PositiveIntegerField(null=True, blank=True)
    home_link_count = models.PositiveIntegerField(null=True, blank=True)
    home_has_app_root = models.BooleanField(null=True, blank=True)
    # Contacts found on the website in the last inspection (stored in `Contact`).
    contacts_found = models.PositiveIntegerField(default=0)
    # Whether its openings are published today, on its website or its job board (`JobOpening`).
    openings_status = models.CharField(
        max_length=20,
        choices=OpeningsStatus.choices,
        default=OpeningsStatus.NOT_CHECKED,
        db_index=True,
    )
    openings_checked_at = models.DateTimeField(null=True, blank=True)
    openings_url = models.URLField(max_length=500, blank=True)
    # Where the company says it is: the schema.org address on its home page, and the office its
    # job board calls headquarters. Evidence for its location (startups/headquarters.py).
    organization_location = models.CharField(max_length=255, blank=True)
    headquarters_location = models.CharField(max_length=255, blank=True)
    error = models.TextField(blank=True)

    def __str__(self):
        return f"{self.startup}: {self.status}"


class JobOpening(models.Model):
    """An opening I look for, published today on the startup's website or job board.

    Each verification replaces the startup's openings: one no longer published disappears.
    Only active ones are kept (those with a date are at most OPENINGS_MAX_AGE_DAYS old), and
    only software roles I look for that require no language besides English and Spanish: the
    rest is discarded (startups/openings.py).
    """

    startup = models.ForeignKey(Startup, on_delete=models.CASCADE, related_name="job_openings")
    title = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True)
    is_remote = models.BooleanField(null=True, blank=True)
    url = models.URLField(max_length=500, blank=True)
    # When the website or the job board published it. Null if they do not say.
    published_at = models.DateTimeField(null=True, blank=True)
    origin = models.CharField(max_length=20, choices=OpeningOrigin.choices)
    # Where it is, of the places its location names, the closest to Madrid. Blank if unknown.
    country = models.CharField(max_length=2, blank=True, help_text="ISO 3166-1 alpha-2")
    timezone_name = models.CharField(max_length=64, blank=True, db_index=True, help_text="IANA")
    # Its description when the job board or the page gives it (plain text or HTML): read to
    # find the languages it requires, and kept to judge it again (`prune_openings`).
    description = models.TextField(blank=True)

    class Meta:
        ordering = [models.F("published_at").desc(nulls_last=True), "title"]

    def __str__(self):
        return f"{self.startup}: {self.title}"


class BlacklistedDomain(models.Model):
    """A site that is not a startup, such as a job board the rules could not tell apart.

    Its startup is discarded and never inspected again; a source that reports it again creates
    it already discarded (startups/blacklist.py).
    """

    domain = models.CharField(max_length=255, unique=True)
    reason = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["domain"]

    def __str__(self):
        return self.domain
