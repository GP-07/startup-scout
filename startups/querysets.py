from datetime import timedelta

from django.db import models
from django.db.models import Case, Exists, OuterRef, Q, When
from django.utils import timezone

from sources.constants import SourceKey
from sources.models import SourceRecord
from startups.constants import HIRING_POST_MAX_AGE_DAYS


class StartupQuerySet(models.QuerySet):
    def with_hiring_signal(self):
        """Annotate whether the startup is hiring, and where that comes from.

        - `has_website_hiring_signal`: its website inspection found open positions.
        - `has_recent_hiring_post`: it posted in "Who is hiring?" within HIRING_POST_MAX_AGE_DAYS.
          An old post says nothing about today.
        - `has_hiring_signal`: either of them.
        """
        oldest_post_date = timezone.now() - timedelta(days=HIRING_POST_MAX_AGE_DAYS)
        recent_hiring_posts = SourceRecord.objects.filter(
            startup=OuterRef("pk"),
            source__key=SourceKey.HACKER_NEWS_HIRING,
            published_at__gte=oldest_post_date,
        )
        return self.annotate(
            has_website_hiring_signal=_true_when(Q(website_inspection__has_hiring_signal=True)),
            has_recent_hiring_post=Exists(recent_hiring_posts),
        ).annotate(
            has_hiring_signal=_true_when(
                Q(has_website_hiring_signal=True) | Q(has_recent_hiring_post=True)
            ),
        )


def _true_when(condition):
    """A strict boolean (never null, even without a related row) for `condition`."""
    return Case(When(condition, then=True), default=False, output_field=models.BooleanField())
