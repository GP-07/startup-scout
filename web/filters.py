"""The startup list: filters from the form and the order in which I review them."""

from django.db.models import Q

from startups.constants import StartupStatus
from startups.models import Startup
from web.constants import FILTER_NO, FILTER_YES


def startup_list_queryset():
    """Every startup with what the list shows, those with a hiring signal first, then newest."""
    return (
        Startup.objects.with_hiring_signal()
        .with_key_contact()
        .prefetch_related("source_records__source")
        .order_by("-has_hiring_signal", "-first_seen_at", "-id")
    )


def filter_startups(queryset, filters):
    """Apply the cleaned data of `StartupFilterForm`."""
    search = filters.get("q")
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search)
            | Q(website__icontains=search)
            | Q(description__icontains=search)
            | Q(domains__domain__icontains=search)
        ).distinct()
    status = filters.get("status")
    if status:
        queryset = queryset.filter(status=status)
    else:
        queryset = queryset.exclude(status=StartupStatus.DISCARDED)
    if filters.get("source"):
        queryset = queryset.filter(source_records__source__key=filters["source"]).distinct()
    if filters.get("country"):
        queryset = queryset.filter(country__iexact=filters["country"])
    queryset = _filter_yes_no(queryset, "has_hiring_signal", filters.get("hiring"))
    queryset = _filter_yes_no(queryset, "has_key_contact", filters.get("has_contact"))
    if filters.get("since"):
        queryset = queryset.filter(first_seen_at__date__gte=filters["since"])
    return queryset


def _filter_yes_no(queryset, annotation, value):
    if value == FILTER_YES:
        return queryset.filter(**{annotation: True})
    if value == FILTER_NO:
        return queryset.filter(**{annotation: False})
    return queryset
