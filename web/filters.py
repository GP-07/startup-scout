"""The startup list: filters from the form and the order in which I review them."""

from django.db.models import Exists, F, OuterRef, Prefetch, Q

from startups.constants import OpeningsStatus, StartupStatus
from startups.models import JobOpening, Startup
from startups.querysets import true_when
from web.constants import (
    ANALYSIS_FILTER_DRAFT,
    ANALYSIS_FILTER_NONE,
    ANALYSIS_FILTER_SENT,
    CONTACT_FILTER_GENERAL,
    CONTACT_FILTER_NONE,
    CONTACT_FILTER_PERSON,
    OPENINGS_FILTER_ALL,
    ORDER_MOST_OPENINGS,
    ORDER_NEWEST,
)


def startup_list_queryset():
    """Every startup with what the list shows: its openings, contacts and analyses."""
    return (
        Startup.objects.with_openings()
        .with_contact_kinds()
        .with_analysis_state()
        .prefetch_related(
            "source_records__source",
            Prefetch("job_openings", queryset=JobOpening.objects.all(), to_attr="openings"),
        )
    )


def filter_startups(queryset, filters):
    """Apply the cleaned data of `StartupFilterForm`, then its order."""
    queryset = _filter_openings(queryset, filters)
    queryset = _filter_text(queryset, filters)
    queryset = _filter_contact(queryset, filters.get("contact"))
    queryset = _filter_analysis(queryset, filters.get("analysis"))
    status = filters.get("status")
    if status:
        queryset = queryset.filter(status=status)
    else:
        queryset = queryset.exclude(status=StartupStatus.DISCARDED)
    if filters.get("source"):
        queryset = queryset.filter(source_records__source__key=filters["source"]).distinct()
    if filters.get("country"):
        queryset = queryset.filter(country__iexact=filters["country"])
    if filters.get("since"):
        queryset = queryset.filter(first_seen_at__date__gte=filters["since"])
    return _order(queryset, filters.get("order"))


def _filter_openings(queryset, filters):
    openings_state = filters.get("openings")
    if openings_state and openings_state != OPENINGS_FILTER_ALL:
        queryset = queryset.filter(openings_state=openings_state)
    if filters.get("role"):
        matching_openings = JobOpening.objects.filter(
            startup=OuterRef("pk"), title__icontains=filters["role"]
        )
        queryset = queryset.filter(Exists(matching_openings))
    if filters.get("remote"):
        queryset = queryset.filter(has_remote_opening=True)
    return queryset


def _filter_text(queryset, filters):
    search = filters.get("q")
    if not search:
        return queryset
    return queryset.filter(
        Q(name__icontains=search)
        | Q(website__icontains=search)
        | Q(description__icontains=search)
        | Q(domains__domain__icontains=search)
    ).distinct()


def _filter_contact(queryset, contact):
    if contact == CONTACT_FILTER_PERSON:
        return queryset.filter(has_person_contact=True)
    if contact == CONTACT_FILTER_GENERAL:
        return queryset.filter(has_person_contact=False, has_general_contact=True)
    if contact == CONTACT_FILTER_NONE:
        return queryset.filter(has_person_contact=False, has_general_contact=False)
    return queryset


def _filter_analysis(queryset, analysis):
    if analysis == ANALYSIS_FILTER_NONE:
        return queryset.filter(has_analysis=False)
    if analysis == ANALYSIS_FILTER_DRAFT:
        return queryset.filter(has_analysis=True, has_sent_analysis=False)
    if analysis == ANALYSIS_FILTER_SENT:
        return queryset.filter(has_sent_analysis=True)
    return queryset


def _order(queryset, order):
    """By default: active openings first, the most recently published first."""
    if order == ORDER_NEWEST:
        return queryset.order_by("-first_seen_at", "-id")
    if order == ORDER_MOST_OPENINGS:
        return queryset.order_by("-openings_count", "-first_seen_at", "-id")
    active_first = Q(openings_state=OpeningsStatus.ACTIVE)
    return queryset.order_by(
        true_when(active_first).desc(),
        F("latest_opening_at").desc(nulls_last=True),
        "-openings_count",
        "-first_seen_at",
        "-id",
    )
