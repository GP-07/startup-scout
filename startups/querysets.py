from django.db import models
from django.db.models import Case, Count, Exists, F, Max, OuterRef, Subquery, Value, When
from django.db.models.functions import Coalesce

from startups.constants import (
    KEY_CONTACT_ROLES,
    PERSON_CONTACT_ROLES,
    ContactRole,
    ContactStatus,
    OpeningsStatus,
)


class StartupQuerySet(models.QuerySet):
    def with_openings(self):
        """Annotate what the startup publishes today (see `JobOpening`).

        - `openings_state`: the `OpeningsStatus` of its last verification (`not_checked` if none).
        - `openings_count`: how many active openings it has.
        - `latest_opening_at`: when its newest dated opening was published.
        - `has_remote_opening`: at least one active opening is remote.
        """
        openings = self._related_model("job_openings").objects.filter(startup=OuterRef("pk"))
        opening_totals = openings.order_by().values("startup")
        return self.annotate(
            openings_state=Coalesce(
                F("website_inspection__openings_status"), Value(OpeningsStatus.NOT_CHECKED)
            ),
            openings_count=Coalesce(
                Subquery(opening_totals.annotate(total=Count("id")).values("total")), 0
            ),
            latest_opening_at=Subquery(
                opening_totals.annotate(latest=Max("published_at")).values("latest")
            ),
            has_remote_opening=Exists(openings.filter(is_remote=True)),
        )

    def with_contact_kinds(self):
        """Annotate `has_person_contact` (CEO, CTO, founder) and `has_general_contact`.

        Rejected contacts do not count, nor does the author of a Hacker News post (role
        "other"): nearly every startup from HN has one.
        """
        contacts = (
            self._related_model("contacts")
            .objects.filter(startup=OuterRef("pk"))
            .exclude(status=ContactStatus.REJECTED)
        )
        return self.annotate(
            has_person_contact=Exists(contacts.filter(role__in=PERSON_CONTACT_ROLES)),
            has_general_contact=Exists(contacts.filter(role=ContactRole.GENERAL)),
            has_key_contact=Exists(contacts.filter(role__in=KEY_CONTACT_ROLES)),
        )

    def with_analysis_state(self):
        """Annotate `has_analysis` and `has_sent_analysis`."""
        analyses = self._related_model("analyses").objects.filter(startup=OuterRef("pk"))
        return self.annotate(
            has_analysis=Exists(analyses),
            has_sent_analysis=Exists(analyses.filter(sent_at__isnull=False)),
        )

    def _related_model(self, relation_name):
        # Resolved through the relation: startups.models imports this module.
        return self.model._meta.get_field(relation_name).related_model


def true_when(condition):
    """A strict boolean (never null, even without a related row) for `condition`."""
    return Case(When(condition, then=True), default=False, output_field=models.BooleanField())
