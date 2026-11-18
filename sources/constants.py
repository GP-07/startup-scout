from django.db import models


class SourceKey(models.TextChoices):
    """Stable source identifiers: stored in the database, mapped to adapters in memory."""

    HACKER_NEWS = "hacker_news", "Hacker News"
    STARTUPXPLORE = "startupxplore", "Startupxplore"
    MANUAL = "manual", "Alta manual"


class SourceRunStatus(models.TextChoices):
    RUNNING = "running", "En curso"
    SUCCEEDED = "succeeded", "OK"
    FAILED = "failed", "Con error"
