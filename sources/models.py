from django.db import models

from sources.constants import SourceKey, SourceRunStatus


class Source(models.Model):
    key = models.SlugField(max_length=50, unique=True, choices=SourceKey.choices)
    name = models.CharField(max_length=100)
    enabled = models.BooleanField(default=True)
    config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class SourceRecord(models.Model):
    """What one source reported about one startup. The startup's fields are merged from these."""

    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="records")
    startup = models.ForeignKey(
        "startups.Startup", on_delete=models.CASCADE, related_name="source_records"
    )
    external_id = models.CharField(max_length=255)
    url = models.URLField(max_length=500, blank=True)
    data = models.JSONField(default=dict, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    # When the source published it (a post, a comment). Null if the source does not say.
    published_at = models.DateTimeField(null=True, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"], name="unique_source_record_per_source"
            ),
        ]

    def __str__(self):
        return f"{self.source.key}:{self.external_id}"


class SourceRun(models.Model):
    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="runs")
    status = models.CharField(
        max_length=20, choices=SourceRunStatus.choices, default=SourceRunStatus.RUNNING
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    items_seen = models.PositiveIntegerField(default=0)
    items_new = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    cursor = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.source.key} @ {self.started_at:%Y-%m-%d %H:%M}"
