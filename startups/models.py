from django.db import models

from startups.constants import (
    ContactFoundVia,
    ContactRole,
    ContactStatus,
    RemotePolicy,
    StartupStatus,
)


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
    first_seen_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

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
